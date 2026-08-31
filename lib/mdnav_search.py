#!/usr/bin/env python3
"""Search rendered mdcat output, and highlight what matched.

Buffer lines carry colour escapes, hyperlinks and whole sixel images, none
of which the reader is searching for. So each line is reduced to its plain
text, with a record of where every byte of that text came from in the
original; matches are found against the plain text and the highlight is
inserted back at the corresponding places, leaving the line's own styling
intact.

Prints one "line occurrence" pair per match -- a line containing the
pattern twice yields two -- and writes a copy of the buffer with every
match highlighted.

Given a line and an occurrence, instead writes just that line with only
that one match highlighted, which is what -g needs: less marks the single
string it found, not every instance of it sharing the line.

usage: mdnav_search.py <buffer-in> <buffer-out> <pattern> <smartcase>
       mdnav_search.py <buffer-in> <buffer-out> <pattern> <smartcase> <line> <occurrence>
"""

import re
import sys

# Colour and mode escapes, OSC (hyperlinks), and DCS (sixel images).
ESCAPES = re.compile(
    rb"\x1b\[[0-9;?]*[ -/]*[@-~]"
    rb"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"
    rb"|\x1bP.*?\x1b\\"
    rb"|\x1b[@-Z\\-_]",
    re.DOTALL,
)

HIGHLIGHT_ON = b"\x1b[7m"
HIGHLIGHT_OFF = b"\x1b[27m"
# The match you are on: reverse video like the others, plus an underline.
# Underline layers over whatever colour the line already had, where a
# different background would fight with it.
ACTIVE_ON = b"\x1b[7;4m"
ACTIVE_OFF = b"\x1b[27;24m"


def plain_and_map(line):
    """The line's visible text, and for each of its bytes the offset in the
    original line where that byte sits."""
    plain = bytearray()
    offsets = []
    pos = 0
    for m in ESCAPES.finditer(line):
        for i in range(pos, m.start()):
            plain.append(line[i])
            offsets.append(i)
        pos = m.end()
    for i in range(pos, len(line)):
        plain.append(line[i])
        offsets.append(i)
    offsets.append(len(line))
    return bytes(plain), offsets


def mark(line, spans, active=None):
    """Wrap each span. `active` names the one to mark as current."""
    marked = bytearray(line)
    _, offsets = plain_and_map(line)
    # Back to front, so earlier offsets stay valid as bytes are inserted.
    for i in range(len(spans) - 1, -1, -1):
        start, end = spans[i]
        on, off = (ACTIVE_ON, ACTIVE_OFF) if i == active else (HIGHLIGHT_ON, HIGHLIGHT_OFF)
        marked[offsets[end]:offsets[end]] = off
        marked[offsets[start]:offsets[start]] = on
    return bytes(marked)


def main():
    src, dst, pattern = sys.argv[1:4]
    smartcase = len(sys.argv) > 4 and sys.argv[4] == "1"
    one = None
    if len(sys.argv) > 6:
        one = (int(sys.argv[5]), int(sys.argv[6]))
    # "only": just the current match, for -g. "emph": every match, with the
    # current one distinguished.
    one_mode = sys.argv[7] if len(sys.argv) > 7 else "only"

    flags = 0
    pat = pattern.encode("utf-8", "replace")
    # less's habit: a pattern typed in lower case is not asking about case.
    if smartcase and not any(c.isupper() for c in pattern):
        flags |= re.IGNORECASE
    try:
        rx = re.compile(pat, flags)
    except re.error:
        return 2

    data = open(src, "rb").read()
    lines = data.split(b"\n")

    if one is not None:
        idx, occ = one
        if idx < 0 or idx >= len(lines):
            return 1
        plain, _ = plain_and_map(lines[idx])
        spans = [m.span() for m in rx.finditer(plain) if m.end() > m.start()]
        if occ < 0 or occ >= len(spans):
            return 1
        with open(dst, "wb") as fh:
            if one_mode == "emph":
                fh.write(mark(lines[idx], spans, active=occ))
            else:
                fh.write(mark(lines[idx], [spans[occ]]))
        return 0

    out = []
    hits = []
    for idx, line in enumerate(lines):
        plain, _ = plain_and_map(line)
        if not plain:
            out.append(line)
            continue
        spans = [m.span() for m in rx.finditer(plain) if m.end() > m.start()]
        if not spans:
            out.append(line)
            continue
        for occ in range(len(spans)):
            hits.append((idx, occ))
        out.append(mark(line, spans))

    with open(dst, "wb") as fh:
        fh.write(b"\n".join(out))
    for idx, occ in hits:
        print(idx, occ)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(2)
