#!/usr/bin/env python3
"""Search rendered mdcat output, and highlight what matched.

Buffer lines carry colour escapes, hyperlinks and whole sixel images, none
of which the reader is searching for. So each line is reduced to its plain
text, with a record of where every byte of that text came from in the
original; matches are found against the plain text and the highlight is
inserted back at the corresponding places, leaving the line's own styling
intact.

Prints the indices of matching lines, one per line, and writes a copy of
the buffer with matches highlighted.

usage: mdnav_search.py <buffer-in> <buffer-out> <pattern> [smartcase]
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


def main():
    src, dst, pattern = sys.argv[1:4]
    smartcase = len(sys.argv) > 4 and sys.argv[4] == "1"

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
    out = []
    hits = []

    for idx, line in enumerate(data.split(b"\n")):
        plain, offsets = plain_and_map(line)
        if not plain:
            out.append(line)
            continue
        spans = [m.span() for m in rx.finditer(plain) if m.end() > m.start()]
        if not spans:
            out.append(line)
            continue

        hits.append(idx)
        marked = bytearray(line)
        # Back to front, so earlier offsets stay valid as bytes are inserted.
        for start, end in reversed(spans):
            marked[offsets[end]:offsets[end]] = HIGHLIGHT_OFF
            marked[offsets[start]:offsets[start]] = HIGHLIGHT_ON
        out.append(bytes(marked))

    with open(dst, "wb") as fh:
        fh.write(b"\n".join(out))
    for h in hits:
        print(h)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(2)
