#!/usr/bin/env python3
"""How many screen rows each buffer line takes.

Nothing is wrapped here. A line wider than the window is left whole and
the terminal wraps it, because a terminal knows a wrapped line is still
one line: select it and it comes back unbroken, which is the difference
between code you can paste and code you cannot. Breaking lines ourselves
would put real newlines in the middle of it.

The cost is that the pager can no longer assume a line is a row, so it
needs to be told how many rows each one will take.

Escapes occupy no columns and a character may occupy two.

An image is asked how tall it is rather than assumed to be one row. It is
one row once sliced, and a whole picture otherwise -- and the difference
is not cosmetic: a line reported as one row that draws ten leaves the
pager scrolling by less than it painted, so the next frame lands on top
of what is still on screen. The escape carries its own geometry, in
pixels for sixel and in rows for kitty, so the same question answers both
cases and neither has to be assumed.

Prints one count per line, in order.

usage: mdnav_spans.py <buffer> <columns> [cell-height]
"""

import re
import sys
import unicodedata

# Sixel raster attributes: "Pan;Pad;Ph;Pv, the last being pixel height.
RASTER = re.compile(rb'"\d+;\d+;(\d+);(\d+)')
# Kitty says it in rows outright.
KITTY_ROWS = re.compile(rb"\x1b_G[^\x1b]*?(?:^|[;,])r=(\d+)")

ESCAPES = re.compile(
    rb"\x1b\[[0-9;?]*[ -/]*[@-~]"
    rb"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"
    rb"|\x1bP.*?\x1b\\"
    rb"|\x1b[@-Z\\-_]",
    re.DOTALL,
)


def char_width(ch):
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def display_width(line):
    text = ESCAPES.sub(b"", line)
    try:
        return sum(char_width(ch) for ch in text.decode("utf-8"))
    except UnicodeDecodeError:
        return len(text)


def image_rows(line, cell_h):
    """Rows an image occupies, from what the escape says about itself."""
    m = RASTER.search(line)
    if m:
        return max(1, -(-int(m.group(2)) // cell_h))
    m = KITTY_ROWS.search(line)
    if m:
        return max(1, int(m.group(1)))
    # Nothing said. One row is the old assumption and the safer of the two
    # guesses: too few rows scrolls short, too many scrolls past content.
    return 1


def main():
    buffer_file, cols = sys.argv[1], int(sys.argv[2])
    cell_h = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    if cols < 1 or cell_h < 1:
        return 1
    out = []
    with open(buffer_file, "rb") as fh:
        for line in fh.read().split(b"\n"):
            if b"\x1bP" in line or b"\x1b_G" in line:
                out.append(image_rows(line, cell_h))
                continue
            width = display_width(line)
            out.append(max(1, -(-width // cols)))
    sys.stdout.write("\n".join(str(n) for n in out) + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(1)
