#!/usr/bin/env python3
"""Generate the complete iconset required by Apple's iconutil."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

ICON_SIZES = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}


def build_iconset(source: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as original:
        image = original.convert("RGBA")
        for filename, size in ICON_SIZES.items():
            resized = image.resize((size, size), Image.Resampling.LANCZOS)
            resized.save(output / filename)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build_iconset(args.source, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
