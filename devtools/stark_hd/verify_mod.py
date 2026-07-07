#!/usr/bin/env python3
"""Full audit of the 0_TLJ4K mod against the game data and the dump tree.

Checks:
  images   — every game XMG has a PNG override: non-indexed, RGBA, dims = 4x
             the original dump, premultiplied (r,g,b <= a for every pixel)
  textures — every unique texture-set location has a .tm.zip whose DDS files
             re-parse under the exact rules of engines/stark/formats/dds.cpp
  videos   — every .sss has a .bik (Bink 1, yuva420p, same fps/frame count),
             every .bbb has a .bbb override (Bink 1, same fps/frame count)
  orphans  — mod files that don't correspond to any original

Usage:
  verify_mod.py --game ~/Documents/TLJHD --dump ~/Documents/TLJ4K-work/dump \
                [--mod-name 0_TLJ4K] [--skip-videos]
"""

import argparse
import json
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from xarc_ls import read_members  # noqa: E402

MODEL_SCALE = 4


class Report:
    def __init__(self):
        self.errors = []
        self.counts = {}

    def err(self, msg):
        self.errors.append(msg)
        print(f"  ERR {msg}")


def ffprobe_stream(path: Path, count_frames=False) -> dict:
    args = ["ffprobe", "-v", "error", "-select_streams", "v:0"]
    if count_frames:
        args += ["-count_frames"]
    args += ["-show_entries", "stream=codec_name,pix_fmt,r_frame_rate,nb_read_frames",
             "-of", "json", str(path)]
    return json.loads(subprocess.check_output(args))["streams"][0]


def check_images(game: Path, dump: Path, mod: Path, rep: Report):
    print("== images ==")
    total = missing = bad = 0
    for archive in sorted(game.rglob("*.xarc")):
        if "mods" in archive.parts:
            continue
        rel_dir = archive.relative_to(game).parent / "xarc"
        for name, _ in read_members(archive):
            if not name.lower().endswith(".xmg"):
                continue
            total += 1
            png_rel = rel_dir / (name[:-4] + ".png")
            override = mod / png_rel
            orig = dump / png_rel
            if not override.exists():
                missing += 1
                rep.err(f"missing override: {png_rel}")
                continue
            try:
                img = Image.open(override)
                if img.mode == "P":
                    bad += 1
                    rep.err(f"indexed PNG (engine rejects): {png_rel}")
                    continue
                with Image.open(orig) as o:
                    ow, oh = o.size
                if img.size != (ow * MODEL_SCALE, oh * MODEL_SCALE):
                    bad += 1
                    rep.err(f"size {img.size} != {MODEL_SCALE}x of {ow}x{oh}: {png_rel}")
                    continue
                arr = np.asarray(img.convert("RGBA"))
                a = arr[..., 3:4]
                if (arr[..., :3] > a).any():
                    bad += 1
                    rep.err(f"not premultiplied (r/g/b > a): {png_rel}")
            except Exception as e:
                bad += 1
                rep.err(f"unreadable {png_rel}: {e}")
    rep.counts["images"] = f"{total - missing - bad}/{total} ok, {missing} missing, {bad} bad"


def parse_dds(data: bytes, name: str, rep: Report) -> bool:
    """Re-parse exactly like engines/stark/formats/dds.cpp."""
    try:
        magic, size = struct.unpack_from("<4sI", data, 0)
        if magic != b"DDS " or size != 124:
            raise ValueError("bad magic/header size")
        flags, h, w = struct.unpack_from("<3I", data, 8)
        if w >= 0x8000 or h >= 0x8000:
            raise ValueError("dimensions >= 0x8000")
        mips = struct.unpack_from("<I", data, 28)[0]
        if not flags & 0x20000:
            mips = 1
        pfsize, pfflags, fourcc, bits, r, g, b, amask = struct.unpack_from("<8I", data, 76)
    except Exception as e:
        rep.err(f"{name}: {e}")
        return False
    if pfflags & 0x4:
        rep.err(f"{name}: fourCC pixel format")
        return False
    if pfflags & 0x20:
        rep.err(f"{name}: indexed")
        return False
    if not pfflags & 0x40:
        rep.err(f"{name}: not RGB")
        return False
    ok24 = not (pfflags & 0x1) and bits == 24 and (r, g, b) == (0xFF0000, 0xFF00, 0xFF)
    ok32 = (pfflags & 0x1) and bits == 32 and (r, g, b, amask) == (0xFF0000, 0xFF00, 0xFF, 0xFF000000)
    if not (ok24 or ok32):
        rep.err(f"{name}: unsupported layout bits={bits} flags={pfflags:#x}")
        return False
    expect = sum((w >> i) * (h >> i) * (bits // 8) for i in range(mips))
    dims_ok = all((w >> i) > 0 and (h >> i) > 0 for i in range(mips))
    if not dims_ok:
        rep.err(f"{name}: mip chain reaches zero dimension")
        return False
    if len(data) - 128 != expect:
        rep.err(f"{name}: data size {len(data)-128} != {expect}")
        return False
    return True


def check_textures(game: Path, mod: Path, rep: Report):
    print("== textures ==")
    total = missing = bad = 0
    for archive in sorted(game.rglob("*.xarc")):
        if "mods" in archive.parts:
            continue
        rel_dir = archive.relative_to(game).parent / "xarc"
        for name, _ in read_members(archive):
            if not name.lower().endswith(".tm"):
                continue
            total += 1
            zip_rel = rel_dir / (name + ".zip")
            zpath = mod / zip_rel
            if not zpath.exists():
                missing += 1
                rep.err(f"missing texture zip: {zip_rel}")
                continue
            try:
                with zipfile.ZipFile(zpath) as zf:
                    dds_names = [n for n in zf.namelist() if n.lower().endswith(".dds")]
                    if not dds_names:
                        bad += 1
                        rep.err(f"no DDS inside: {zip_rel}")
                        continue
                    for n in dds_names:
                        if not parse_dds(zf.read(n), f"{zip_rel}:{n}", rep):
                            bad += 1
            except Exception as e:
                bad += 1
                rep.err(f"unreadable zip {zip_rel}: {e}")
    rep.counts["texture sets"] = f"{total - missing - bad}/{total} ok, {missing} missing, {bad} bad"


def check_videos(game: Path, mod: Path, rep: Report):
    print("== videos ==")
    for ext, out_ext, want_alpha, label in ((".sss", ".bik", True, "sss"), (".bbb", ".bbb", False, "bbb")):
        files = sorted(p for p in game.rglob(f"*{ext}") if "mods" not in p.parts and "_lo_res" not in p.name)
        total = len(files)
        missing = bad = 0
        for src in files:
            rel = src.relative_to(game)
            target = mod / rel.parent / (src.stem + out_ext)
            if not target.exists():
                missing += 1
                rep.err(f"missing video: {rel.parent}/{src.stem}{out_ext}")
                continue
            try:
                st = ffprobe_stream(target, count_frames=True)
                so = ffprobe_stream(src, count_frames=True)
                if st["codec_name"] != "binkvideo":
                    raise ValueError(f"codec {st['codec_name']}")
                if want_alpha and st["pix_fmt"] != "yuva420p":
                    raise ValueError(f"no alpha ({st['pix_fmt']})")
                def as_fps(s):
                    num, den = s.split("/")
                    return int(num) / int(den)
                if abs(as_fps(st["r_frame_rate"]) - as_fps(so["r_frame_rate"])) > 0.01:
                    raise ValueError(f"fps {st['r_frame_rate']} != {so['r_frame_rate']}")
                if st["nb_read_frames"] != so["nb_read_frames"]:
                    raise ValueError(f"frames {st['nb_read_frames']} != {so['nb_read_frames']}")
            except Exception as e:
                bad += 1
                rep.err(f"{rel.parent}/{src.stem}{out_ext}: {e}")
        rep.counts[f"videos {label}"] = f"{total - missing - bad}/{total} ok, {missing} missing, {bad} bad"


def check_orphans(game: Path, dump: Path, mod: Path, rep: Report):
    print("== orphans ==")
    orphans = 0
    for f in mod.rglob("*"):
        if not f.is_file() or f.name.startswith("."):
            continue
        rel = f.relative_to(mod)
        ok = False
        if f.suffix == ".png":
            ok = (dump / rel).exists()
        elif f.name.endswith(".tm.zip"):
            ok = (dump / rel.parent / rel.name[:-4]).exists()
        elif f.suffix == ".bik":
            ok = (game / rel.parent / (f.stem + ".sss")).exists()
        elif f.suffix == ".bbb":
            ok = (game / rel).exists()
        elif f.suffix in (".md", ".txt"):
            ok = True
        if not ok:
            orphans += 1
            rep.err(f"orphan: {rel}")
    rep.counts["orphans"] = str(orphans)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, default=Path.home() / "Documents/TLJHD")
    parser.add_argument("--dump", type=Path, default=Path.home() / "Documents/TLJ4K-work/dump")
    parser.add_argument("--mod-name", default="0_TLJ4K")
    parser.add_argument("--skip-videos", action="store_true", help="пропустить долгую проверку видео")
    args = parser.parse_args()

    mod = args.game / "mods" / args.mod_name
    rep = Report()
    check_images(args.game, args.dump, mod, rep)
    check_textures(args.game, mod, rep)
    if not args.skip_videos:
        check_videos(args.game, mod, rep)
    check_orphans(args.game, args.dump, mod, rep)

    print("\n=== SUMMARY ===")
    for k, v in rep.counts.items():
        print(f"{k:14s} {v}")
    print(f"{'errors':14s} {len(rep.errors)}")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
