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
    try:
        with open(anchors_file, encoding="utf-8") as fh:
            text = json.load(fh).get(slug.lstrip("#"))
    except (OSError, ValueError):
        return 1
    if not text:
        return 1

    want = normalise(text)
    if not want:
        return 1
    with open(buffer_file, "rb") as fh:
        for index, raw in enumerate(fh.read().split(b"\n")):
            # The whole line, not a part of it: "References" must not be
            # answered by a line mentioning preferences.
            if normalise(ESCAPES.sub(b"", raw).decode("utf-8", "replace")) == want:
                print(index)
                return 0
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(1)
