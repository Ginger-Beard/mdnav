#!/usr/bin/env python3
"""How many screen rows each buffer line takes.

Nothing is wrapped here. A line wider than the window is left whole and
the terminal wraps it, because a terminal knows a wrapped line is still
one line: select it and it comes back unbroken, which is the difference
between code you can paste and code you cannot. Breaking lines ourselves
would put real newlines in the middle of it.

The cost is that the pager can no longer assume a line is a row, so it
needs to be told how many rows each one will take.

Escapes occupy no columns and a character may occupy two; a line carrying
an image is one row whatever it contains.

Prints one count per line, in order.

usage: mdnav_spans.py <buffer> <columns>
"""

import re
import sys
import unicodedata

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


def main():
    buffer_file, cols = sys.argv[1], int(sys.argv[2])
    if cols < 1:
        return 1
    out = []
    with open(buffer_file, "rb") as fh:
        for line in fh.read().split(b"\n"):
            if b"\x1bP" in line or b"\x1b_G" in line:
                out.append(1)
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
