#!/usr/bin/env python3
"""Wrap buffer lines too wide for the terminal.

mdcat wraps prose to the width it is given, but never code: reflowing a
code block would misrepresent it. Long code lines therefore arrive wider
than the screen, and a pager drawing one buffer line per row loses
whatever runs past the edge.

Wrapping them here keeps the one-row-per-line arithmetic the rest of the
pager depends on -- a wrapped line simply becomes several lines.

Escape sequences are not text: they are stepped over rather than counted,
and whatever styling is in force at a break is closed and reopened, so a
colour spanning a wrap does not bleed or stop halfway. Lines carrying an
image are left alone; they are one row by construction.

usage: mdnav_wrap.py <buffer-in> <buffer-out> <columns>
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
SGR = re.compile(rb"\x1b\[([0-9;]*)m")
RESET = b"\x1b[0m"


def char_width(ch):
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def wrap_line(line, cols):
    """Split one line into pieces at most `cols` columns wide."""
    out = []
    piece = bytearray()
    width = 0
    style = b""          # SGR sequences in force at the current point
    pos = 0

    def flush(carry_style):
        nonlocal piece, width
        if carry_style and style:
            out.append(bytes(piece) + RESET)
        else:
            out.append(bytes(piece))
        piece = bytearray()
        width = 0
        if carry_style and style:
            piece.extend(style)

    while pos < len(line):
        m = ESCAPES.match(line, pos)
        if m:
            seq = m.group(0)
            piece.extend(seq)
            sgr = SGR.fullmatch(seq)
            if sgr:
                # An empty or zero parameter clears what came before.
                params = sgr.group(1)
                if params in (b"", b"0"):
                    style = b""
                else:
                    style += seq
            pos = m.end()
            continue

        # One character, however many bytes UTF-8 spends on it.
        end = pos + 1
        while end < len(line) and 0x80 <= line[end] < 0xC0:
            end += 1
        raw = line[pos:end]
        try:
            w = char_width(raw.decode("utf-8"))
        except UnicodeDecodeError:
            w = 1

        if width + w > cols and width > 0:
            flush(True)
        piece.extend(raw)
        width += w
        pos = end

    out.append(bytes(piece))
    return out


def main():
    src, dst, cols = sys.argv[1:4]
    cols = int(cols)
    if cols < 2:
        return 1

    data = open(src, "rb").read()
    out = []
    for line in data.split(b"\n"):
        # An image is a row of its own and cannot be split.
        if b"\x1bP" in line or b"\x1b_G" in line:
            out.append(line)
            continue
        out.extend(wrap_line(line, cols))

    with open(dst, "wb") as fh:
        fh.write(b"\n".join(out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(1)
