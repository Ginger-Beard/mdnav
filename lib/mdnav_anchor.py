#!/usr/bin/env python3
"""Find the line a document's own anchor points at.

A link to `#section` names a place in the file being read, not a file.
Handed to the desktop it becomes a path that exists nowhere; resolved
here it is somewhere to scroll to.

The anchor names a heading, so its text is looked for in the rendered
buffer -- which is what the reader is actually looking at, wrapped and
styled as it will appear.

Prints the line index, or exits non-zero if the anchor names nothing.

usage: mdnav_anchor.py <anchors-json> <slug> <buffer>
"""

import json
import re
import sys

ESCAPES = re.compile(
    rb"\x1b\[[0-9;?]*[ -/]*[@-~]"
    rb"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"
    rb"|\x1bP.*?\x1b\\"
    rb"|\x1b[@-Z\\-_]",
    re.DOTALL,
)


def normalise(text):
    """A heading reduced to its words, so the rendered line and the source
    heading can be compared. mdcat draws headings with rules and markers
    around them, and those are not part of the name."""
    text = text.strip().lower()
    text = re.sub(r"^[^\w]+", "", text)
    text = re.sub(r"[^\w]+$", "", text)
    return re.sub(r"\s+", " ", text)


def main():
    anchors_file, slug, buffer_file = sys.argv[1:4]
    # "#section|21": the section to find, and the item within it to prefer.
    slug, _, item = slug.lstrip("#").partition("|")
    try:
        with open(anchors_file, encoding="utf-8") as fh:
            anchors = json.load(fh)
    except (OSError, ValueError):
        return 1
    text = anchors.get(slug)
    if not text:
        # A document that spelled the anchor with one hyphen where the
        # heading gives two. Taken only when it names a single heading.
        short = re.sub(r"-+", "-", slug)
        near = [v for k, v in anchors.items() if re.sub(r"-+", "-", k) == short]
        if len(near) != 1:
            return 1
        text = near[0]

    want = normalise(text)
    if not want:
        return 1

    lines = [normalise(ESCAPES.sub(b"", raw).decode("utf-8", "replace"))
             for raw in open(buffer_file, "rb").read().split(b"\n")]

    heading = None
    for index, line in enumerate(lines):
        # The whole line, not a part of it: "References" must not be
        # answered by a line mentioning preferences.
        if line == want:
            heading = index
            break
    if heading is None:
        return 1

    if item:
        # The item as the section lists it: "- [21] Title" reduces to
        # "21 title". Only below the heading, and only in what follows it.
        for index in range(heading + 1, min(len(lines), heading + 500)):
            # "- [21] Title" reduces to "21] title": the number is there,
            # but whatever punctuation the list uses comes straight after
            # it, so match the number as a word rather than a prefix.
            if re.match(re.escape(item) + r"\b", lines[index]):
                print(index)
                return 0

    print(heading)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(1)
