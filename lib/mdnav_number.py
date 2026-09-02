#!/usr/bin/env python3
"""Number the lines of a file being shown as a page.

The numbers cannot go in before rendering: inside a code fence they become
part of the code, and the highlighter then sees `1  import os`, which is
not Python and is not coloured. So they go on afterwards, down the left of
lines the renderer has already coloured.

A file's lines and the lines it renders to are one for one -- code is
never re-wrapped -- so the last `count` lines that are not trailing blanks
are its lines, in order.

usage: mdnav_number.py <buffer> <count>
"""

import sys

DIM = b"\x1b[2m"
UNDIM = b"\x1b[22m"


def main():
    buffer_file, count = sys.argv[1], int(sys.argv[2])
    if count < 1:
        return 0

    with open(buffer_file, "rb") as handle:
        lines = handle.read().split(b"\n")

    end = len(lines) - 1
    while end >= 0 and not lines[end].strip():
        end -= 1
    start = end - count + 1
    if start < 0:
        return 0

    width = len(str(count))
    for offset in range(count):
        number = str(offset + 1).rjust(width).encode("ascii")
        # Reset first: the line carries the renderer's own colours, and the
        # number is not part of what it is colouring.
        lines[start + offset] = (
            b"\x1b[0m" + DIM + number + UNDIM + b"  " + lines[start + offset])

    with open(buffer_file, "wb") as handle:
        handle.write(b"\n".join(lines))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
