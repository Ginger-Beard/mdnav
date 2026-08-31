#!/usr/bin/env python3
"""Rewrite a Markdown file so mdcat emits links mdnav can intercept.

Two problems this solves:

1. mdcat resolves relative links against the *rendered* file's directory, and
   we render a temp copy, so relative targets would break. Everything local
   becomes absolute.

2. mdcat rewrites bare file:// URLs to include the hostname (file://host/path),
   which is correct per the OSC 8 spec but unopenable on Windows/WSL. A custom
   scheme passes through untouched, so local links become mdnav://<abs path>.

Images keep plain filesystem paths -- mdcat reads those off disk itself rather
than handing them to the terminal.
"""

import json
import os
import re
import sys
from urllib.parse import quote

IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(\s+\"[^\"]*\")?\)")
LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)(\s+\"[^\"]*\")?\)")
URL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def main():
    src, out_md, out_links, scheme = sys.argv[1:5]
    # Which mdnav rendered this. Carried in the URI so a click goes back to
    # the window it was clicked in, however many are running.
    instance = os.environ.get("MDNAV_INSTANCE", "")
    # "marker" leaves a placeholder line for each image, to be replaced with
    # sliced strips after rendering; "inline" lets mdcat draw them itself.
    image_mode = sys.argv[5] if len(sys.argv) > 5 else "inline"
    out_images = sys.argv[6] if len(sys.argv) > 6 else None
    srcdir = os.path.dirname(os.path.realpath(src))
    text = open(src, encoding="utf-8").read()
    links = []
    images = []

    def local_path(target):
        """Absolute path for a local target, or None if it isn't one."""
        if URL_RE.match(target) or target.startswith("#"):
            return None
        path = target.split("#", 1)[0]
        if not path:
            return None
        return os.path.realpath(os.path.join(srcdir, path))

    def fix_image(m):
        alt, target, title = m.group(1), m.group(2), m.group(3) or ""
        path = local_path(target)
        if path is None:
            return m.group(0)
        if image_mode == "marker":
            # A paragraph of its own, so it renders as one line that can be
            # swapped for the image's strips afterwards.
            images.append(path)
            return "\n\nMDNAVIMG:{}:\n\n".format(len(images) - 1)
        return "![{}]({}{})".format(alt, path, title)

    def fix_link(m):
        label, target, title = m.group(1), m.group(2), m.group(3) or ""
        path = local_path(target)
        if path is None:
            return m.group(0)
        links.append({"label": label, "path": path})
        uri = "{}://{}{}".format(scheme, instance, quote(path))
        return "[{}]({}{})".format(label, uri, title)

    text = IMAGE_RE.sub(fix_image, text)
    text = LINK_RE.sub(fix_link, text)

    with open(out_md, "w", encoding="utf-8") as f:
        f.write(text)
    with open(out_links, "w", encoding="utf-8") as f:
        json.dump(links, f)
    if out_images:
        with open(out_images, "w", encoding="utf-8") as f:
            json.dump(images, f)


if __name__ == "__main__":
    main()
