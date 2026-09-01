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
import os
import re
import sys

DEBUG = os.environ.get("MDNAV_DEBUG", "")


def note(fmt, *args):
    if not DEBUG:
        return
    try:
        with open(DEBUG, "a", encoding="utf-8") as fh:
            fh.write("mdnav: table links: " + fmt.format(*args) + "\n")
    except OSError:
        pass


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


def linked_ranges(line):
    """Byte ranges of the line already covered by a link."""
    spans = []
    open_at = None
    pos = 0
    while pos < len(line):
        m = OSC8.match(line, pos)
        if m:
            if m.group(1):
                open_at = m.start()
            elif open_at is not None:
                spans.append((open_at, m.end()))
                open_at = None
            pos = m.end()
            continue
        pos += 1
    if open_at is not None:
        spans.append((open_at, len(line)))
    return spans


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


def table_regions(lines):
    """The line range of each table drawn, in the order they were drawn.

    A rule opens one; it runs to the last rule before the blank line that
    ends it, which keeps a cell spanning several lines inside the table
    and a paragraph after it outside.
    """
    regions = []
    index = 0
    while index < len(lines):
        if not is_rule(lines[index]):
            index += 1
            continue
        last_rule = index
        scan = index + 1
        while scan < len(lines) and lines[scan].strip():
            if is_rule(lines[scan]):
                last_rule = scan
            scan += 1
        # A rule with no row beneath it is not a table. A box drawn inside
        # a code block is made of the same characters, and counted as a
        # table it shifts every table after it by one -- which is not a
        # link left plain but a link put in the wrong place.
        if any(lines[j].strip() and not is_rule(lines[j])
               for j in range(index, last_rule + 1)):
            regions.append((index, last_rule))
        index = max(scan, last_rule + 1)
    return regions


def main():
    buffer_file, links_file = sys.argv[1:3]
    try:
        with open(links_file, encoding="utf-8") as fh:
            links = json.load(fh)
    except (OSError, ValueError):
        return 0

    # The label as drawn, not as written: a cell shows "Bold Doc" where the
    # document said "**Bold Doc**", and it is the drawn form being searched.

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

    # Counted against every link, not only the ones in tables: the same
    # target may be linked from a paragraph as well, and that link's
    # hyperlink is not the table's. Each one emitted is credited to the
    # earliest link that asked for it, which is the one that got it.
    #
    # Only a link in a table is ever put back. Everywhere else a link
    # survives rendering, so a missing one is not a thing to go hunting
    # for by its text.
    missing = []
    for link in links:
        uri = link.get("uri")
        if not uri:
            continue
        # Only a link outside a table can have been the one emitted: a
        # link inside one is never emitted at all, which is the whole
        # reason for this. Letting it take the credit would leave it
        # looking present and plain, and which one that is depends on
        # nothing more visible than where the target was first mentioned.
        if link.get("table") is None and present.get(uri):
            present[uri] -= 1
            continue
        if link.get("table") is not None and (
                link.get("text") or link.get("label", "")).strip():
            missing.append(link)
    if not missing:
        return 0

    regions = table_regions(
        [ESCAPES.sub(b"", l).decode("utf-8", "replace") for l in lines])
    # The nth table written is the nth table drawn, so the two have to
    # count the same. Too few and a link would be looked for in a table
    # that is not there; too many and every table after the surplus one is
    # off by one, which is not a link left plain but a link put in the
    # wrong place. Either way there is nothing trustworthy to do.
    written = None
    try:
        with open(links_file + ".tables", encoding="utf-8") as fh:
            written = json.load(fh)
    except (OSError, ValueError):
        written = None
    if written is not None and written != len(regions):
        note("{} tables written, {} drawn -- leaving them alone",
             written, len(regions))
        return 0
    if not regions or max(l["table"] for l in missing) >= len(regions):
        return 0

    # Insertions are collected first and applied from the back, so an
    # earlier offset is still an offset into the line it was measured in.
    edits = {}
    taken = set()
    for link in missing:
        label = " ".join((link.get("text") or link["label"]).split())
        if not label:
            continue
        # Only within the table this link was written in. Searching past
        # the end of it would let a link whose text the layout wrapped --
        # and which therefore cannot be found at all -- be answered by the
        # same words in a later table, pointing that one somewhere wrong.
        first, last = regions[link["table"]]
        placed = False
        for index in range(first, last + 1):
            text, offsets = plain(lines[index])
            # Two links can share a row, so a row is searched from the
            # column after the last one claimed in it, not from its start.
            from_col = 0
            while True:
                at = text.find(label, from_col)
                if at < 0:
                    break
                before = text[at - 1] if at else " "
                after = text[at + len(label)] if at + len(label) < len(text) else " "
                if (before.isalnum() and label[:1].isalnum()) or (
                        after.isalnum() and label[-1:].isalnum()):
                    # "5" is in "2015" without being it.
                    from_col = at + 1
                    continue
                begin, finish = offsets[at], offsets[at + len(label)]
                covered = any(a <= begin and finish <= b
                              for a, b in linked_ranges(lines[index]))
                if not covered and (index, at) not in taken:
                    taken.add((index, at))
                    edits.setdefault(index, []).append(
                        (begin, finish, link["uri"]))
                    placed = True
                    break
                from_col = at + 1
            if placed:
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
    except Exception as error:
        # Failing here costs the table its links and nothing else, so it is
        # not worth stopping over -- but it went unnoticed once already, so
        # it says so where the rest of the tracing goes.
        debug = os.environ.get("MDNAV_DEBUG", "")
        if debug:
            try:
                with open(debug, "a", encoding="utf-8") as fh:
                    fh.write("mdnav: table links: {}\n".format(error))
            except OSError:
                pass
        sys.exit(0)
