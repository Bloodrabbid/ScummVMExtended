#!/usr/bin/env python3
"""Batch-convert all TLJ videos into the HD mod.

  batch_videos.py sss   — 439 scene videos (.sss): SPAN upscale, alpha, Bink 1
  batch_videos.py bbb   — 62 FMVs (.bbb): Topaz Iris v2, Bink 1 + BinkAudio

Resumable: files whose mod output already exists and validates are skipped.
Heavy intermediates are deleted after each video.

Requires: CrossOver bottle "RAD" with RAD Video Tools, and for bbb —
Topaz Video installed and licensed.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from upscale import color_bleed, pick_device, run_model_tiled  # noqa: E402
from video_pipeline import decode_frames, ffprobe_fps  # noqa: E402

GAME = Path("/Users/udinkirill/Documents/TLJHD")
MOD = GAME / "mods/0_TLJ4K"
WORK = Path("/Users/udinkirill/Documents/TLJ4K-work/video/batch")
MODELS = Path(__file__).parent / "models"
SPAN = MODELS / "4xNomosUni_span.safetensors"

WINE = "/Applications/CrossOver.app/Contents/SharedSupport/CrossOver/bin/wine"
RADVIDEO = "C:\\Program Files (x86)\\RADVideo\\radvideo64.exe"
TOPAZ_FFMPEG = "/Applications/Topaz Video.app/Contents/MacOS/ffmpeg"
TOPAZ_ENV = {
    "TVAI_MODEL_DIR": "/Applications/Topaz Video.app/Contents/Resources/models",
    "TVAI_MODEL_DATA_DIR": str(Path.home() / "Library/Application Support/Topaz Labs LLC/Topaz Video"),
}
CYAN = (0, 255, 255)


def winpath(p: Path) -> str:
    return "Z:" + str(p).replace("/", "\\")


def rad(tool: str, *args: str):
    subprocess.check_call(
        [WINE, "--bottle", "RAD", "--wait-children", "--", RADVIDEO, tool, *args, "/#"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def probe(path: Path) -> dict:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
        "-show_entries", "stream=codec_name,pix_fmt,r_frame_rate,nb_read_frames",
        "-of", "json", str(path)])
    return json.loads(out)["streams"][0]


def validate(encoded: Path, fps: float, frames: int, want_alpha: bool) -> list[str]:
    st = probe(encoded)
    problems = []
    if st["codec_name"] != "binkvideo":
        problems.append(f"codec {st['codec_name']}")
    if want_alpha and st["pix_fmt"] != "yuva420p":
        problems.append(f"no alpha ({st['pix_fmt']})")
    num, den = st["r_frame_rate"].split("/")
    if abs(int(num) / int(den) - fps) > 0.01:
        problems.append(f"fps {st['r_frame_rate']}")
    if int(st["nb_read_frames"]) != frames:
        problems.append(f"frames {st['nb_read_frames']} != {frames}")
    return problems


def already_done(target: Path, src: Path, want_alpha: bool) -> bool:
    if not target.exists():
        return False
    try:
        frames = int(probe(src)["nb_read_frames"])
        return not validate(target, ffprobe_fps(src), frames, want_alpha)
    except Exception:
        return False


def write_tga_sequence(frames_dir: Path, tga_dir: Path, premultiply: bool):
    tga_dir.mkdir(parents=True, exist_ok=True)
    for f in sorted(frames_dir.glob("f*.png")):
        img = Image.open(f)
        if premultiply:
            arr = np.asarray(img.convert("RGBA")).astype(np.uint16)
            a = arr[..., 3:4]
            arr[..., :3] = (arr[..., :3] * a + 127) // 255
            img = Image.fromarray(arr.astype(np.uint8), "RGBA")
        else:
            img = img.convert("RGB")
        img.save(tga_dir / (f.stem + ".tga"))


def binkc(tga_dir: Path, n_frames: int, out: Path, fps: float, alpha: bool):
    pattern = winpath(tga_dir / "f?????.tga") + f"*1-{n_frames}"
    args = [pattern, winpath(out), "/V100", f"/F{fps:g}", "/O"]
    if alpha:
        args.append("/Z1000")
    rad("binkc", *args)


def cleanup(workdir: Path):
    for sub in ("raw", "src", "up", "tga"):
        shutil.rmtree(workdir / sub, ignore_errors=True)


def run_sss(limit: int | None):
    device, dtype = pick_device()
    from spandrel import ModelLoader
    model = ModelLoader().load_from_file(str(SPAN)).to(device=device, dtype=dtype).eval()
    print(f"SPAN on {device.type}")

    files = sorted(p for p in GAME.rglob("*.sss") if "mods" not in p.parts)
    print(f"{len(files)} scene videos")
    done = failed = skipped = 0

    for i, src in enumerate(files):
        rel = src.relative_to(GAME)
        target = MOD / rel.parent / (src.stem + ".bik")
        if already_done(target, src, want_alpha=True):
            skipped += 1
            continue

        workdir = WORK / "sss" / str(rel.parent).replace("/", "_") / src.stem
        try:
            fps = ffprobe_fps(src)
            frames = decode_frames(src, workdir / "raw")

            (workdir / "up").mkdir(parents=True, exist_ok=True)
            with torch.inference_mode():
                for f in sorted((workdir / "raw").glob("f*.png")):
                    rgb = np.asarray(Image.open(f).convert("RGB"))
                    mask = np.all(rgb == CYAN, axis=-1)
                    alpha = np.where(mask, 0, 255).astype(np.uint8)
                    up_rgb = run_model_tiled(model, color_bleed(rgb, alpha), device, dtype, 512, 32)
                    up_a = run_model_tiled(model, np.repeat(alpha[..., None], 3, axis=2),
                                           device, dtype, 512, 32)[..., 0]
                    Image.fromarray(np.dstack([up_rgb, up_a]), "RGBA").save(workdir / "up" / f.name)

            write_tga_sequence(workdir / "up", workdir / "tga", premultiply=True)
            binkc(workdir / "tga", frames, target, fps, alpha=True)

            problems = validate(target, fps, frames, want_alpha=True)
            if problems:
                raise RuntimeError("; ".join(problems))
            cleanup(workdir)
            done += 1
            print(f"[{i+1}/{len(files)}] OK {rel} ({frames}f @{fps:g})", flush=True)
        except Exception as e:
            failed += 1
            target.unlink(missing_ok=True)
            print(f"[{i+1}/{len(files)}] FAIL {rel}: {e}", flush=True)
        if limit and done >= limit:
            break

    print(f"sss: {done} done, {skipped} already ok, {failed} failed")


def run_bbb(limit: int | None):
    files = sorted((GAME / "Global/xarc").glob("*.bbb"))
    files = [f for f in files if "_lo_res" not in f.name]
    print(f"{len(files)} FMVs")
    done = failed = skipped = 0

    for i, src in enumerate(files):
        target = MOD / "Global/xarc" / src.name
        if already_done(target, src, want_alpha=False):
            skipped += 1
            continue

        workdir = WORK / "bbb" / src.stem
        try:
            fps = ffprobe_fps(src)
            frames = decode_frames(src, workdir / "src")
            has_audio = subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn",
                 "-acodec", "pcm_s16le", str(workdir / "audio.wav")]).returncode == 0

            (workdir / "up").mkdir(parents=True, exist_ok=True)
            subprocess.check_call(
                [TOPAZ_FFMPEG, "-hide_banner", "-v", "error", "-y",
                 "-framerate", f"{fps:g}", "-start_number", "1",
                 "-i", str(workdir / "src" / "f%05d.png"),
                 "-vf", "tvai_up=model=iris-2:scale=4",
                 "-start_number", "1", str(workdir / "up" / "f%05d.png")],
                env={**os.environ, **TOPAZ_ENV})
            n_up = len(list((workdir / "up").glob("f*.png")))
            if n_up != frames:
                raise RuntimeError(f"topaz frames {n_up} != {frames}")

            write_tga_sequence(workdir / "up", workdir / "tga", premultiply=False)
            video_bik = workdir / "video.bik"
            binkc(workdir / "tga", frames, video_bik, fps, alpha=False)
            if has_audio:
                rad("binkmix", winpath(video_bik), winpath(workdir / "audio.wav"), winpath(target))
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(video_bik, target)

            problems = validate(target, fps, frames, want_alpha=False)
            if problems:
                raise RuntimeError("; ".join(problems))
            cleanup(workdir)
            video_bik.unlink(missing_ok=True)
            done += 1
            print(f"[{i+1}/{len(files)}] OK {src.name} ({frames}f @{fps:g})", flush=True)
        except Exception as e:
            failed += 1
            target.unlink(missing_ok=True)
            print(f"[{i+1}/{len(files)}] FAIL {src.name}: {e}", flush=True)
        if limit and done >= limit:
            break

    print(f"bbb: {done} done, {skipped} already ok, {failed} failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["sss", "bbb"])
    parser.add_argument("--limit", type=int, help="stop after N successful videos (для проб)")
    args = parser.parse_args()

    free_gb = shutil.disk_usage(WORK.parent if WORK.parent.exists() else Path.home()).free / 1e9
    if args.stage == "bbb" and free_gb < 60:
        print(f"WARNING: только {free_gb:.0f} ГБ свободно — промежуточные кадры FMV могут не влезть")

    MOD.mkdir(parents=True, exist_ok=True)
    (run_sss if args.stage == "sss" else run_bbb)(args.limit)


if __name__ == "__main__":
    main()
