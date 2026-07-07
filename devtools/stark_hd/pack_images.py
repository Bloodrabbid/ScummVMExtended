#!/usr/bin/env python3
"""Package upscaled PNGs into a Stark mod directory.

Takes the original dump tree (for size validation) and the upscaled tree,
premultiplies alpha (the engine's 2D pipeline blends with
GL_ONE / GL_ONE_MINUS_SRC_ALPHA), optionally downsamples for the handheld
profile, and writes the mod tree mirroring the dump layout.

Texture-set folders (*.tm/) are skipped — those are packaged by
make_dds_zips.py into zip archives instead.

Usage:
  pack_images.py --dump dump --up up4x --mod <GameDir>/mods/0_TLJ4K [--scale-div 2]
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


def premultiply(img: Image.Image) -> Image.Image:
    arr = np.asarray(img.convert("RGBA")).astype(np.uint16)
    a = arr[..., 3:4]
    arr[..., :3] = (arr[..., :3] * a + 127) // 255
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", required=True, help="original dump tree (validation reference)")
    parser.add_argument("--up", required=True, help="upscaled tree (straight alpha, 4x)")
    parser.add_argument("--mod", required=True, help="mod output directory")
    parser.add_argument("--scale-div", type=int, default=1,
                        help="integer divisor applied to the 4x masters (2 = handheld profile)")
    parser.add_argument("--model-scale", type=int, default=4)
    parser.add_argument("--smooth-alpha", type=float, default=0, metavar="RADIUS",
                        help="round the staircase silhouettes of near-binary alpha masks: "
                             "gaussian blur of RADIUS px (at 4x) + a soft threshold. Images "
                             "with genuine alpha gradients (translucent panels) are detected "
                             "and left untouched")
    args = parser.parse_args()

    dump, up, mod = Path(args.dump), Path(args.up), Path(args.mod)

    sources = sorted(up.rglob("*.png"))
    packed = errors = 0
    for src in sources:
        rel = src.relative_to(up)
        if any(part.endswith(".tm") for part in rel.parts):
            continue

        orig = dump / rel
        if not orig.exists():
            print(f"ORPHAN (no original): {rel}")
            errors += 1
            continue

        img = Image.open(src)
        with Image.open(orig) as o:
            ow, oh = o.size
        if (img.width, img.height) != (ow * args.model_scale, oh * args.model_scale):
            print(f"SIZE MISMATCH {rel}: {img.size} vs {ow}x{oh} * {args.model_scale}")
            errors += 1
            continue

        if args.scale_div > 1:
            img = img.resize((img.width // args.scale_div, img.height // args.scale_div),
                             Image.LANCZOS)

        if args.smooth_alpha > 0:
            img = img.convert("RGBA")
            a = np.asarray(img.getchannel("A"))
            partial = ((a > 16) & (a < 240)).mean()
            if a.min() < 255 and partial < 0.05:  # near-binary mask, not a translucent panel
                blurred = img.getchannel("A").filter(ImageFilter.GaussianBlur(args.smooth_alpha))
                arr = np.asarray(blurred, dtype=np.float32)
                arr = np.clip((arr - 96) / 64, 0, 1) * 255
                img.putalpha(Image.fromarray(arr.astype(np.uint8), "L"))

        img = premultiply(img)

        dst = mod / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        img.save(dst)
        packed += 1
        if packed % 200 == 0:
            print(f"  {packed}/{len(sources)}", flush=True)

    print(f"packed {packed} images into {mod}, {errors} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
