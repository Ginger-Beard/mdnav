#!/usr/bin/env python3
"""Cut every image in rendered mdcat output down to one-row-tall strips.

A sixel image is a single escape sequence of whatever height the terminal
decides, which makes it impossible for a pager to account for and
impossible to draw part of. Sliced into strips one text row tall, each
strip is an ordinary line: the row arithmetic is exact, and a
partly-scrolled image is simply the strips that fall inside the window.

This works on mdcat's *output* rather than its input, so it catches
everything mdcat draws as an image -- Markdown images, but also Mermaid
diagrams and rendered maths, which never appear as image syntax in the
source and so cannot be intercepted before rendering.

Images no taller than one row are left alone; so is anything that cannot
be decoded, which then behaves as it did before.

usage: mdnav_slice.py <buffer-in> <buffer-out> <cell-height> <cache-dir>
"""

import glob
import hashlib
import os
import re
import subprocess
import sys
import tempfile

# A sixel image: DCS ... ST.
BLOB = re.compile(rb"\x1bP.*?\x1b\\", re.DOTALL)
# Raster attributes carry the pixel size: "Pan;Pad;Ph;Pv
RASTER = re.compile(rb'"\d+;\d+;(\d+);(\d+)')


def strip_height(blob):
    m = RASTER.search(blob)
    return int(m.group(2)) if m else 0


def slice_blob(blob, cell_h, cache_dir):
    """Strips for one image, or None if it cannot be sliced."""
    key = hashlib.sha1(blob).hexdigest() + "-{}".format(cell_h)
    cached = os.path.join(cache_dir, key + ".strips")
    if os.path.exists(cached):
        with open(cached, "rb") as fh:
            return [ln for ln in fh.read().split(b"\n") if ln]

    try:
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "in.six")
            with open(src, "wb") as fh:
                fh.write(blob)
            png = os.path.join(td, "in.png")
            subprocess.run(["convert", src, png], check=True, capture_output=True)
            subprocess.run(
                ["convert", png, "-crop", "x{}".format(cell_h), "+repage",
                 os.path.join(td, "s_%04d.png")],
                check=True, capture_output=True,
            )
            files = sorted(glob.glob(os.path.join(td, "s_*.png")))
            if not files:
                return None
            # Cropping to files and encoding them in one batch is an order of
            # magnitude faster than fusing both into a single command.
            encoded = subprocess.run(
                ["convert"] + files + ["sixel:-"],
                check=True, capture_output=True,
            ).stdout
    except Exception:
        return None

    strips = [b"\x1bP" + p for p in encoded.split(b"\x1bP") if p.strip()]
    strips = [s.replace(b"\n", b"") for s in strips]
    if not strips:
        return None

    os.makedirs(cache_dir, exist_ok=True)
    tmp = cached + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(b"\n".join(strips) + b"\n")
    os.replace(tmp, cached)
    return strips


def main():
    src, dst, cell_h, cache_dir = sys.argv[1:5]
    cell_h = int(cell_h)
    if cell_h < 1:
        return 1

    data = open(src, "rb").read()
    out = []

    for line in data.split(b"\n"):
        blobs = list(BLOB.finditer(line))
        tall = [m for m in blobs if strip_height(m.group(0)) > cell_h]
        if not tall:
            out.append(line)
            continue

        # Text sharing the line with a tall image cannot stay beside it, so
        # it becomes its own line above and below.
        pos = 0
        for m in tall:
            before = line[pos:m.start()]
            if before.strip():
                out.append(before)
            strips = slice_blob(m.group(0), cell_h, cache_dir)
            if strips is None:
                out.append(m.group(0))
            else:
                out.extend(strips)
            pos = m.end()
        rest = line[pos:]
        if rest.strip():
            out.append(rest)

    with open(dst, "wb") as fh:
        fh.write(b"\n".join(out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(1)
