#!/usr/bin/env python3
"""Package upscaled texture sets into DDS zip overrides for the Stark engine.

For every '<set>.tm/' folder in the upscaled tree, writes a
'<same relative path>/<set>.tm.zip' into the mod directory, containing one
uncompressed DDS per texture with a full mipmap chain. The engine looks these
up location-scoped first ('<lvl>/<loc>/xarc/<set>.tm.zip'), then at the mod
root.

The DDS writer produces exactly what engines/stark/formats/dds.cpp accepts:
uncompressed BGR24 (or BGRA32 when a texture actually has transparency),
R/G/B masks 0x00FF0000/0x0000FF00/0x000000FF, tightly packed rows,
mip dimensions halving without clamping (so the level count stops before any
dimension reaches zero).

Usage:
  make_dds_zips.py --dump dump --up up4x --mod <GameDir>/mods/0_TLJ4K [--scale-div 2]
"""

import argparse
import struct
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

DDSD_FLAGS = 0x1 | 0x2 | 0x4 | 0x8 | 0x1000 | 0x20000  # CAPS|HEIGHT|WIDTH|PITCH|PIXELFORMAT|MIPMAPCOUNT
DDPF_ALPHAPIXELS = 0x1
DDPF_RGB = 0x40
DDSCAPS = 0x00401008  # TEXTURE|MIPMAP|COMPLEX


def build_dds(img: Image.Image) -> bytes:
    has_alpha = img.mode == "RGBA" and np.asarray(img)[..., 3].min() < 255
    img = img.convert("RGBA" if has_alpha else "RGB")
    w, h = img.size
    assert w & (w - 1) == 0 and h & (h - 1) == 0, f"non power-of-two texture {w}x{h}"

    bpp = 4 if has_alpha else 3
    mip_count = min(w, h).bit_length()  # log2(min)+1: last level is Nx1 or 1xN, never 0

    header = struct.pack(
        "<4s7I44x",
        b"DDS ", 124, DDSD_FLAGS, h, w, w * bpp, 0, mip_count)
    header += struct.pack(
        "<9I16x",
        32,
        DDPF_RGB | (DDPF_ALPHAPIXELS if has_alpha else 0),
        0,
        bpp * 8,
        0x00FF0000, 0x0000FF00, 0x000000FF,
        0xFF000000 if has_alpha else 0,
        DDSCAPS)
    assert len(header) == 128

    data = bytearray()
    level = img
    for i in range(mip_count):
        if i > 0:
            level = img.resize((max(1, w >> i), max(1, h >> i)), Image.LANCZOS)
        arr = np.asarray(level)
        bgr = arr[..., [2, 1, 0]]  # B, G, R byte order
        if has_alpha:
            bgr = np.dstack([bgr, arr[..., 3]])
        data += bgr.tobytes()

    return bytes(header) + bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", required=True, help="original dump tree (validation reference)")
    parser.add_argument("--up", required=True, help="upscaled tree (4x)")
    parser.add_argument("--mod", required=True, help="mod output directory")
    parser.add_argument("--scale-div", type=int, default=1,
                        help="integer divisor applied to the 4x masters (2 = handheld profile)")
    parser.add_argument("--model-scale", type=int, default=4)
    args = parser.parse_args()

    dump, up, mod = Path(args.dump), Path(args.up), Path(args.mod)

    zips = textures = errors = 0
    for set_dir in sorted(p for p in up.rglob("*.tm") if p.is_dir()):
        rel = set_dir.relative_to(up)
        zip_path = mod / rel.parent / (rel.name + ".zip")
        zip_path.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
            for src in sorted(set_dir.glob("*.png")):
                orig = dump / rel / src.name
                img = Image.open(src)
                if orig.exists():
                    with Image.open(orig) as o:
                        expect = (o.width * args.model_scale, o.height * args.model_scale)
                    if img.size != expect:
                        print(f"SIZE MISMATCH {rel}/{src.name}: {img.size} vs {expect}")
                        errors += 1
                        continue
                else:
                    print(f"ORPHAN (no original): {rel}/{src.name}")
                    errors += 1
                    continue

                if args.scale_div > 1:
                    img = img.resize((img.width // args.scale_div, img.height // args.scale_div),
                                     Image.LANCZOS)

                try:
                    dds = build_dds(img)
                except AssertionError as e:
                    print(f"SKIP {rel}/{src.name}: {e}")
                    errors += 1
                    continue

                zf.writestr(src.stem + ".dds", dds)
                textures += 1
        zips += 1

    print(f"wrote {zips} texture set zips ({textures} textures) into {mod}, {errors} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
