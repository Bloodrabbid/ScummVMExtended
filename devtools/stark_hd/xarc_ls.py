#!/usr/bin/env python3
"""List members of Stark XARC archives (The Longest Journey).

Usage:
  xarc_ls.py <archive.xarc> [...]        list members of given archives
  xarc_ls.py --census <game_dir> [--ext .xmg]
                                         walk all *.xarc under game_dir and
                                         print per-archive member counts and
                                         a total, optionally filtered by
                                         extension
"""

import argparse
import struct
import sys
from pathlib import Path


def read_members(archive: Path):
    """Yield (name, length) for each member of an XARC archive."""
    with archive.open("rb") as f:
        unknown, count, _first_offset = struct.unpack("<III", f.read(12))
        if unknown != 1:
            print(f"warning: {archive}: header unknown={unknown}", file=sys.stderr)
        for _ in range(count):
            name = bytearray()
            while (c := f.read(1)) not in (b"", b"\x00"):
                name += c
            length, _member_unknown = struct.unpack("<II", f.read(8))
            yield name.decode("latin-1"), length


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="archives, or game dir with --census")
    parser.add_argument("--census", action="store_true", help="walk all *.xarc under a directory")
    parser.add_argument("--ext", help="only count members with this extension (e.g. .xmg)")
    args = parser.parse_args()

    if args.census:
        game_dir = Path(args.paths[0])
        total = 0
        names = {}  # member name -> list of (archive, size)
        for archive in sorted(game_dir.rglob("*.xarc")):
            if "mods" in archive.parts:
                continue
            members = [
                (n, l) for n, l in read_members(archive)
                if not args.ext or n.lower().endswith(args.ext.lower())
            ]
            if members:
                print(f"{archive.relative_to(game_dir)}: {len(members)}")
                total += len(members)
                for n, l in members:
                    names.setdefault(n.lower(), []).append((str(archive.relative_to(game_dir)), l))
        print(f"total: {total}, unique names: {len(names)}")
        dup_diverging = {
            n: occ for n, occ in names.items()
            if len(occ) > 1 and len({size for _, size in occ}) > 1
        }
        if dup_diverging:
            print(f"duplicate names with DIFFERENT sizes: {len(dup_diverging)}")
            for n, occ in sorted(dup_diverging.items()):
                print(f"  {n}: {occ}")
    else:
        for path in args.paths:
            for name, length in read_members(Path(path)):
                print(f"{length:10d}  {name}")


if __name__ == "__main__":
    main()
