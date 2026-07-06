#!/usr/bin/env python3
"""Batch neural upscaler for The Longest Journey assets.

Loads any spandrel-compatible model (OpenModelDB .pth/.safetensors) and
upscales PNGs, preserving the directory layout of the input tree.

Alpha handling: RGB is color-bled into fully transparent regions before
inference (XMG decodes transparency as black, which would smear dark halos),
then RGB and the alpha channel (as grayscale) are upscaled separately and
recombined. Output PNGs use straight (non-premultiplied) alpha; pack_images.py
premultiplies at packaging time.

Usage:
  upscale.py --model models/4xNomos8kSC.safetensors --in dump/1e --out up/1e
  upscale.py --model ... --in img1.png img2.png --out outdir [--suffix _nomos]
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from spandrel import ImageModelDescriptor, ModelLoader


def pick_device():
    if torch.backends.mps.is_available():
        return torch.device("mps"), torch.float16
    return torch.device("cpu"), torch.float32


def color_bleed(rgb: np.ndarray, alpha: np.ndarray, max_iters: int = 64) -> np.ndarray:
    """Fill fully-transparent pixels with the color of their nearest opaque
    neighbors (iterative 4-neighbor dilation), so the model never sees the
    black filler XMG puts under transparency."""
    known = alpha > 0
    if known.all():
        return rgb
    if not known.any():
        return rgb

    out = rgb.astype(np.float32).copy()
    out[~known] = 0.0
    mask = known.astype(np.float32)

    for _ in range(max_iters):
        if mask.all():
            break
        # Sum of known neighbors in 4 directions
        acc = np.zeros_like(out)
        cnt = np.zeros_like(mask)
        for axis, shift in ((0, 1), (0, -1), (1, 1), (1, -1)):
            acc += np.roll(out * mask[..., None], shift, axis=axis)
            cnt += np.roll(mask, shift, axis=axis)
        newly = (mask == 0) & (cnt > 0)
        if not newly.any():
            break
        out[newly] = acc[newly] / cnt[newly][..., None]
        mask[newly] = 1.0

    if not mask.all():
        # Distant interior of large transparent regions: use average known color
        avg = rgb[known].mean(axis=0)
        out[mask == 0] = avg

    return np.clip(out, 0, 255).astype(np.uint8)


@torch.inference_mode()
def run_model_tiled(model, img: np.ndarray, device, dtype, tile: int, overlap: int) -> np.ndarray:
    """img: HxWx3 uint8 -> upscaled HxWx3 uint8."""
    scale = model.scale
    h, w, _ = img.shape
    out = np.zeros((h * scale, w * scale, 3), dtype=np.float32)

    def infer(patch: np.ndarray) -> np.ndarray:
        t = torch.from_numpy(patch.astype(np.float32) / 255.0)
        t = t.permute(2, 0, 1).unsqueeze(0).to(device=device, dtype=dtype)
        r = model(t)
        r = r.squeeze(0).permute(1, 2, 0).clamp(0, 1).float().cpu().numpy()
        return r * 255.0

    if h <= tile and w <= tile:
        return np.clip(infer(img), 0, 255).astype(np.uint8)

    step = tile - 2 * overlap
    for y0 in range(0, h, step):
        for x0 in range(0, w, step):
            # Tile with context margins, clamped to the image
            ty0, tx0 = max(0, y0 - overlap), max(0, x0 - overlap)
            ty1, tx1 = min(h, y0 + step + overlap), min(w, x0 + step + overlap)
            res = infer(img[ty0:ty1, tx0:tx1])
            # Paste only the central (non-margin) region
            cy0, cx0 = y0, x0
            cy1, cx1 = min(h, y0 + step), min(w, x0 + step)
            out[cy0 * scale:cy1 * scale, cx0 * scale:cx1 * scale] = \
                res[(cy0 - ty0) * scale:(cy1 - ty0) * scale,
                    (cx0 - tx0) * scale:(cx1 - tx0) * scale]

    return np.clip(out, 0, 255).astype(np.uint8)


def upscale_file(model, src: Path, dst: Path, device, dtype, tile: int, overlap: int,
                 post_scale: float | None) -> str:
    img = Image.open(src)
    if img.mode == "P":
        img = img.convert("RGBA")
    has_alpha = img.mode in ("RGBA", "LA")
    img = img.convert("RGBA") if has_alpha else img.convert("RGB")
    arr = np.asarray(img)

    if has_alpha and (arr[..., 3] == 255).all():
        has_alpha = False
        arr = arr[..., :3]

    if has_alpha:
        rgb, alpha = arr[..., :3], arr[..., 3]
        rgb = color_bleed(rgb, alpha)
        up_rgb = run_model_tiled(model, rgb, device, dtype, tile, overlap)
        alpha3 = np.repeat(alpha[..., None], 3, axis=2)
        up_alpha = run_model_tiled(model, alpha3, device, dtype, tile, overlap)[..., 0]
        result = np.dstack([up_rgb, up_alpha])
        mode = "RGBA"
    else:
        rgb = arr[..., :3]
        result = run_model_tiled(model, rgb, device, dtype, tile, overlap)
        mode = "RGB"

    out_img = Image.fromarray(result, mode)
    if post_scale and post_scale != 1.0:
        out_img = out_img.resize(
            (round(out_img.width * post_scale), round(out_img.height * post_scale)),
            Image.LANCZOS)

    dst.parent.mkdir(parents=True, exist_ok=True)
    out_img.save(dst)
    return mode


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="spandrel-compatible model file")
    parser.add_argument("--in", dest="inputs", nargs="+", required=True,
                        help="input directory (recursed for *.png) or PNG files")
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument("--suffix", default="", help="suffix added before .png in output names")
    parser.add_argument("--tile", type=int, default=512)
    parser.add_argument("--overlap", type=int, default=32)
    parser.add_argument("--post-scale", type=float, default=None,
                        help="Lanczos resize factor applied after the model (e.g. 0.5 for 2x from a 4x model)")
    parser.add_argument("--force", action="store_true", help="ignore the resume manifest")
    args = parser.parse_args()

    torch.manual_seed(0)
    device, dtype = pick_device()

    model_path = Path(args.model)
    model = ModelLoader().load_from_file(str(model_path))
    assert isinstance(model, ImageModelDescriptor), "not an image-to-image model"
    model = model.to(device=device, dtype=dtype).eval()
    print(f"model: {model_path.name} ({model.architecture.name}, {model.scale}x) on {device.type}/{dtype}")

    # Collect (src, relative destination) pairs
    jobs: list[tuple[Path, Path]] = []
    for inp in map(Path, args.inputs):
        if inp.is_dir():
            for src in sorted(inp.rglob("*.png")):
                jobs.append((src, src.relative_to(inp)))
        else:
            jobs.append((inp, Path(inp.name)))

    out_root = Path(args.out)
    manifest_path = out_root / ".upscale-manifest.json"
    manifest = {}
    if manifest_path.exists() and not args.force:
        manifest = json.loads(manifest_path.read_text())

    done = skipped = 0
    started = time.time()
    for i, (src, rel) in enumerate(jobs):
        if args.suffix:
            rel = rel.with_name(rel.stem + args.suffix + rel.suffix)
        dst = out_root / rel
        key = str(rel)
        digest = f"{sha1_file(src)}:{model_path.name}:{args.post_scale}"

        if manifest.get(key) == digest and dst.exists():
            skipped += 1
            continue

        try:
            upscale_file(model, src, dst, device, dtype, args.tile, args.overlap, args.post_scale)
        except Exception as e:  # noqa: BLE001 - report and continue the batch
            print(f"FAIL {src}: {e}", file=sys.stderr)
            continue

        manifest[key] = digest
        done += 1
        if done % 25 == 0:
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(json.dumps(manifest, indent=0))
            rate = done / (time.time() - started)
            print(f"  {done}/{len(jobs)} ({rate:.2f} img/s)")

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=0))
    print(f"done: {done} upscaled, {skipped} up-to-date, {len(jobs) - done - skipped} failed")


if __name__ == "__main__":
    main()
