#!/usr/bin/env python3
"""Where every link sits on the screen.

A hyperlink is written into the buffer as OSC 8 -- a sequence naming the
target, the text it covers, then a sequence closing it -- which says
nothing about where that text lands once drawn. Working out the columns is
this file's job, so that a position on screen can be turned back into the
link under it.

Escapes occupy no columns, and a character may occupy two, so neither byte
nor character offsets will do.

Prints one link per line: line index, first column, last column, target.

usage: mdnav_links.py <buffer>
"""

import re
import sys
import unicodedata

OSC8 = re.compile(rb"\x1b\]8;;([^\x1b\x07]*)(?:\x07|\x1b\\)")
OTHER_ESCAPES = re.compile(
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


def links_in(line):
    """(first column, last column, target) for each link on the line."""
    found = []
    col = 1
    pos = 0
    open_at = None
    target = None

    while pos < len(line):
        m = OSC8.match(line, pos)
        if m:
            uri = m.group(1)
            if uri:
                open_at, target = col, uri
            elif open_at is not None:
                found.append((open_at, col - 1, target))
                open_at, target = None, None
            pos = m.end()
            continue

        m = OTHER_ESCAPES.match(line, pos)
        if m:
            pos = m.end()
            continue

        end = pos + 1
        while end < len(line) and 0x80 <= line[end] < 0xC0:
            end += 1
        try:
            col += char_width(line[pos:end].decode("utf-8"))
        except UnicodeDecodeError:
            col += 1
        pos = end

    # A link left open at the end of the line still covers what it reached.
    if open_at is not None:
        found.append((open_at, col - 1, target))
    return found


def main():
    with open(sys.argv[1], "rb") as fh:
        for index, line in enumerate(fh.read().split(b"\n")):
            if b"\x1b]8;;" not in line:
                continue
            for start, end, target in links_in(line):
                if end >= start:
                    print("{}\t{}\t{}\t{}".format(
                        index, start, end, target.decode("utf-8", "replace")))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(1)
