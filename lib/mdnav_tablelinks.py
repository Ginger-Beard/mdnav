#!/usr/bin/env python3
"""Put back the links a renderer dropped inside table cells.

mdcat takes a link's style into a table cell and leaves its destination
behind: the text is printed and coloured, and nothing is clickable. The
destination is not recoverable from the rendered output, but it does not
have to be -- the rewriter knew it, wrote it, and recorded it, so what
came out can be compared with what went in and the difference put back.

Nothing is guessed. A link is re-attached only where the text of a link
that went missing is found inside a table, in the order the links were
written. Restricting it to a table matters: a heading or a paragraph may
say the same words, and making a heading clickable would be worse than
leaving a cell plain -- an anchor is found by looking for a heading that
is not a link.

Whatever the renderer did emit is left untouched, so if a version comes
along that carries destinations into cells, this finds nothing missing
and does nothing.

usage: mdnav_tablelinks.py <buffer> <links.json>
"""

import json
import re
import sys

OSC8 = re.compile(rb"\x1b\]8;;([^\x1b\x07]*)(?:\x07|\x1b\\)")
ESCAPES = re.compile(
    rb"\x1b\]8;;[^\x1b\x07]*(?:\x07|\x1b\\)"
    rb"|\x1b\[[0-9;?]*[ -/]*[@-~]"
    rb"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"
    rb"|\x1bP.*?\x1b\\"
    rb"|\x1b[@-Z\\-_]",
    re.DOTALL,
)
RULE_CHARS = set("─━╌┄┈")


def plain(line):
    """The line's text, and where each character of it sits in the bytes."""
    text = []
    offsets = []
    pos = 0
    while pos < len(line):
        m = ESCAPES.match(line, pos)
        if m:
            pos = m.end()
            continue
        end = pos + 1
        while end < len(line) and 0x80 <= line[end] < 0xC0:
            end += 1
        text.append(line[pos:end].decode("utf-8", "replace"))
        offsets.append(pos)
        pos = end
    offsets.append(len(line))
    return "".join(text), offsets


def is_rule(text):
    stripped = text.strip()
    return bool(stripped) and set(stripped) <= RULE_CHARS


def table_rows(lines):
    """Indices of lines inside a table.

    A rule opens one; it runs to the last rule before the blank line that
    ends it, which keeps a cell spanning several lines inside the table
    and a paragraph after it outside.
    """
    inside = set()
    index = 0
    while index < len(lines):
        if not is_rule(lines[index]):
            index += 1
            continue
        start = index
        last_rule = index
        scan = index + 1
        while scan < len(lines) and lines[scan].strip():
            if is_rule(lines[scan]):
                last_rule = scan
            scan += 1
        inside.update(range(start, last_rule + 1))
        index = max(scan, last_rule + 1)
    return inside


def main():
    buffer_file, links_file = sys.argv[1:3]
    try:
        with open(links_file, encoding="utf-8") as fh:
            links = json.load(fh)
    except (OSError, ValueError):
        return 0

    # The label as drawn, not as written: a cell shows "Bold Doc" where the
    # document said "**Bold Doc**", and it is the drawn form being searched.
    wanted = [l for l in links
              if l.get("uri") and (l.get("text") or l.get("label", "")).strip()]
    if not wanted:
        return 0

    with open(buffer_file, "rb") as fh:
        raw = fh.read()
    lines = raw.split(b"\n")

    # What the renderer did emit, so only what it dropped is put back.
    present = {}
    for line in lines:
        for m in OSC8.finditer(line):
            uri = m.group(1).decode("utf-8", "replace")
            if uri:
                present[uri] = present.get(uri, 0) + 1

    missing = []
    for link in wanted:
        uri = link["uri"]
        if present.get(uri):
            present[uri] -= 1
        else:
            missing.append(link)
    if not missing:
        return 0

    rows = table_rows([ESCAPES.sub(b"", l).decode("utf-8", "replace") for l in lines])
    if not rows:
        return 0

    # Insertions are collected first and applied from the back, so an
    # earlier offset is still an offset into the line it was measured in.
    edits = {}
    taken = set()
    search_from = 0
    for link in missing:
        label = " ".join((link.get("text") or link["label"]).split())
        if not label:
            continue
        placed = False
        for index in sorted(i for i in rows if i >= search_from):
            text, offsets = plain(lines[index])
            start = 0
            while True:
                at = text.find(label, start)
                if at < 0:
                    break
                if (index, at) not in taken:
                    taken.add((index, at))
                    edits.setdefault(index, []).append(
                        (offsets[at], offsets[at + len(label)], link["uri"]))
                    placed = True
                    break
                start = at + 1
            if placed:
                # Later links are looked for from here on, so the rows are
                # walked once and in the order the links were written.
                search_from = index
                break

    if not edits:
        return 0

    for index, spans in edits.items():
        line = lines[index]
        for begin, end, uri in sorted(spans, reverse=True):
            opener = b"\x1b]8;;" + uri.encode("utf-8") + b"\x1b\\"
            line = line[:begin] + opener + line[begin:end] + b"\x1b]8;;\x1b\\" + line[end:]
        lines[index] = line

    with open(buffer_file, "wb") as fh:
        fh.write(b"\n".join(lines))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
