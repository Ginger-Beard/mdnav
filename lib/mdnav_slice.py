#!/usr/bin/env python3
"""Slice an image into sixel strips exactly one text row tall.

A sixel image is normally one escape sequence of whatever height the
terminal decides, which makes it impossible to account for in a pager and
impossible to draw partially. Sliced into one-row strips, each strip is an
ordinary line: the row arithmetic is exact, and a partly-scrolled image is
simply the strips that fall inside the window.

Writes one strip per line (sixel data contains no newlines, so this is
safe) and prints the path of that file. Results are cached, since encoding
a tall image runs to a second or so.

usage: mdnav_slice.py <image> <cell-width> <cell-height> <columns> <cache-dir>
"""

import glob
import hashlib
import os
import subprocess
import sys
import tempfile


def main():
    img, cell_w, cell_h, cols, cache_dir = sys.argv[1:6]
    cell_w, cell_h, cols = int(cell_w), int(cell_h), int(cols)
    if cell_h < 1 or cell_w < 1 or cols < 1:
        return 1

    real = os.path.realpath(img)
    st = os.stat(real)
    key = hashlib.sha1(
        "{}|{}|{}|{}x{}|{}".format(
            real, st.st_mtime_ns, st.st_size, cell_w, cell_h, cols
        ).encode()
    ).hexdigest()

    os.makedirs(cache_dir, exist_ok=True)
    out = os.path.join(cache_dir, key + ".strips")
    if os.path.exists(out):
        print(out)
        return 0

    max_px = cols * cell_w
    with tempfile.TemporaryDirectory() as td:
        pattern = os.path.join(td, "s_%04d.png")
        # Cropping to files and then encoding them in one batch is an order
        # of magnitude faster than fusing both into a single command, which
        # re-quantises per frame.
        subprocess.run(
            ["convert", real, "-resize", "{}x>".format(max_px),
             "-crop", "x{}".format(cell_h), "+repage", pattern],
            check=True, capture_output=True,
        )
        files = sorted(glob.glob(os.path.join(td, "s_*.png")))
        if not files:
            return 1
        encoded = subprocess.run(
            ["convert"] + files + ["sixel:-"],
            check=True, capture_output=True,
        ).stdout

    strips = [b"\x1bP" + part for part in encoded.split(b"\x1bP") if part.strip()]
    if not strips:
        return 1

    tmp = out + ".tmp"
    with open(tmp, "wb") as fh:
        for strip in strips:
            fh.write(strip.replace(b"\n", b"") + b"\n")
    os.replace(tmp, out)
    print(out)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(1)
