#!/usr/bin/env python3
"""Video pipeline for TLJ HD mod: decode -> (upscale.py) -> TGA for Bink encode.

Stages (per video):
  prep-sss  <in.sss> <workdir>   decode Smacker frames, cyan-key -> straight alpha
  prep-bbb  <in.bbb> <workdir>   decode Bink frames + extract WAV audio
  finalize  <workdir>            premultiply upscaled frames, write TGA sequence
  check     <encoded.bik> --workdir <workdir> [--install <mod path>]
                                 validate codec/fps/frame count, then install

Between prep and finalize run the upscaler:
  upscale.py --model models/realesr-general-x4v3.pth --in <workdir>/src --out <workdir>/up

The Bink encode itself runs in RAD Video Tools (CrossOver/Parallels/Windows):
open <workdir>/tga/f00001.tga, "Bink it!", format Bink 1, force frame rate from
<workdir>/meta.json, alpha plane "include and leave unchanged" (already
premultiplied), then for .bbb mix <workdir>/audio.wav via the binkmix tool.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

CYAN = (0, 255, 255)


def ffprobe_fps(path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", str(path)])
    num, den = out.decode().strip().split("/")
    return int(num) / int(den)


def decode_frames(path: Path, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.check_call([
        "ffmpeg", "-v", "error", "-y", "-i", str(path),
        "-fps_mode", "passthrough", "-pix_fmt", "rgb24",
        str(out_dir / "f%05d.png")])
    return len(list(out_dir.glob("f*.png")))


def write_meta(workdir: Path, **kwargs):
    (workdir / "meta.json").write_text(json.dumps(kwargs, indent=2))
    print(json.dumps(kwargs, indent=2))


def cmd_prep_sss(args):
    src, workdir = Path(args.input), Path(args.workdir)
    frames = decode_frames(src, workdir / "raw")

    # Cyan (0,255,255) is the Smacker transparency key; move it to the alpha
    # channel (straight alpha; upscale.py color-bleeds RGB under a=0 itself)
    cyan_frames = 0
    (workdir / "src").mkdir(parents=True, exist_ok=True)
    for f in sorted((workdir / "raw").glob("f*.png")):
        rgb = np.asarray(Image.open(f).convert("RGB"))
        mask = np.all(rgb == CYAN, axis=-1)
        if mask.any():
            cyan_frames += 1
        alpha = np.where(mask, 0, 255).astype(np.uint8)
        rgba = np.dstack([rgb, alpha])
        Image.fromarray(rgba, "RGBA").save(workdir / "src" / f.name)

    write_meta(workdir, kind="sss", name=src.stem, source=str(src),
               fps=ffprobe_fps(src), frames=frames,
               alpha=cyan_frames > 0, cyan_frames=cyan_frames)


def cmd_prep_bbb(args):
    src, workdir = Path(args.input), Path(args.workdir)
    frames = decode_frames(src, workdir / "src")  # opaque: raw == src

    has_audio = subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn",
        "-acodec", "pcm_s16le", str(workdir / "audio.wav")]).returncode == 0

    write_meta(workdir, kind="bbb", name=src.stem, source=str(src),
               fps=ffprobe_fps(src), frames=frames,
               alpha=False, audio=bool(has_audio))


def cmd_finalize(args):
    workdir = Path(args.workdir)
    meta = json.loads((workdir / "meta.json").read_text())
    up = workdir / "up"
    tga = workdir / "tga"
    tga.mkdir(exist_ok=True)

    files = sorted(up.glob("f*.png"))
    assert len(files) == meta["frames"], f"frame count mismatch: {len(files)} != {meta['frames']}"

    for f in files:
        img = Image.open(f)
        if meta["alpha"]:
            arr = np.asarray(img.convert("RGBA")).astype(np.uint16)
            a = arr[..., 3:4]
            arr[..., :3] = (arr[..., :3] * a + 127) // 255  # premultiply
            img = Image.fromarray(arr.astype(np.uint8), "RGBA")
        else:
            img = img.convert("RGB")
        img.save(tga / (f.stem + ".tga"))

    print(f"TGA sequence: {tga}/f00001.tga ({len(files)} frames)")
    print("RAD Video Tools:")
    print(f"  - format: Bink 1, force frame rate to {meta['fps']:g}")
    if meta["alpha"]:
        print("  - alpha: include input video's alpha plane, leave unchanged")
    if meta.get("audio"):
        print(f"  - then mix sound: radvideo64.exe binkmix <out.bik> {workdir/'audio.wav'} <final>")


def cmd_check(args):
    encoded, workdir = Path(args.encoded), Path(args.workdir)
    meta = json.loads((workdir / "meta.json").read_text())

    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-count_frames", "-show_entries",
        "stream=codec_name,pix_fmt,r_frame_rate,nb_read_frames",
        "-of", "json", str(encoded)])
    st = json.loads(out)["streams"][0]

    problems = []
    if st["codec_name"] != "binkvideo":
        problems.append(f"codec is {st['codec_name']}, engine only decodes Bink 1 ('binkvideo')")
    if meta["alpha"] and st["pix_fmt"] != "yuva420p":
        problems.append(f"pix_fmt {st['pix_fmt']}: alpha plane missing (need yuva420p)")
    num, den = st["r_frame_rate"].split("/")
    if abs(int(num) / int(den) - meta["fps"]) > 0.01:
        problems.append(f"fps {st['r_frame_rate']} != {meta['fps']:g}")
    if int(st["nb_read_frames"]) != meta["frames"]:
        problems.append(f"frames {st['nb_read_frames']} != {meta['frames']}")

    if problems:
        print("FAIL:\n  " + "\n  ".join(problems))
        return 1

    print(f"OK: binkvideo, {st['pix_fmt']}, {st['r_frame_rate']} fps, {st['nb_read_frames']} frames")
    if args.install:
        dst = Path(args.install)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(encoded.read_bytes())
        print(f"installed -> {dst}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prep-sss"); p.add_argument("input"); p.add_argument("workdir")
    p.set_defaults(func=cmd_prep_sss)
    p = sub.add_parser("prep-bbb"); p.add_argument("input"); p.add_argument("workdir")
    p.set_defaults(func=cmd_prep_bbb)
    p = sub.add_parser("finalize"); p.add_argument("workdir")
    p.set_defaults(func=cmd_finalize)
    p = sub.add_parser("check"); p.add_argument("encoded")
    p.add_argument("--workdir", required=True); p.add_argument("--install")
    p.set_defaults(func=cmd_check)

    args = parser.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
