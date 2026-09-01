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
    """Split one line into pieces at most `cols` columns wide.

    Breaks at a space where there is one, as mdcat does with prose, rather
    than at whatever column the limit falls on -- a word split down the
    middle reads as damage. A single run longer than the window has no
    space to break at and is split where it must be.
    """
    items = []           # (bytes, width, is_space)
    pos = 0
    while pos < len(line):
        m = ESCAPES.match(line, pos)
        if m:
            items.append((m.group(0), 0, False))
            pos = m.end()
            continue
        end = pos + 1
        while end < len(line) and 0x80 <= line[end] < 0xC0:
            end += 1
        raw = line[pos:end]
        try:
            ch = raw.decode("utf-8")
            w = char_width(ch)
            space = ch == " "
        except UnicodeDecodeError:
            w, space = 1, False
        items.append((raw, w, space))
        pos = end

    def style_after(start, seq):
        """The styling in force after a run of items, given what preceded."""
        style = start
        for raw, _, _ in seq:
            sgr = SGR.fullmatch(raw)
            if sgr:
                style = b"" if sgr.group(1) in (b"", b"0") else style + raw
        return style

    out = []
    current = []
    width = 0
    line_style = b""     # what is in force where this line begins
    last_space = -1

    def emit(chunk, start_style):
        body = b"".join(raw for raw, _, _ in chunk)
        tail = RESET if style_after(start_style, chunk) else b""
        out.append(start_style + body + tail)

    for item in items:
        raw, w, space = item
        if w and width + w > cols and current:
            if last_space > 0:
                # Break at the space, which is dropped rather than left
                # hanging at the end of the line.
                head, tail = current[:last_space], current[last_space + 1:]
            else:
                # Nowhere to break: a single run wider than the window.
                head, tail = current, []
            emit(head, line_style)
            line_style = style_after(line_style, head)
            current = tail
            width = sum(x[1] for x in tail)
            last_space = -1
        if space:
            last_space = len(current)
        current.append(item)
        width += w

    emit(current, line_style)
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
