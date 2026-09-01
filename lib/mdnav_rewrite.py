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
# mdBook's cross-reference directive, which a preprocessor would replace
# before rendering. Read raw -- as anyone browsing such a repository is --
# it is a dead line of text naming a file. Turned into a link, it is the
# thing worth following.
REF_RE = re.compile(r"\{\{#ref\}\}\s*(\S+)\s*\{\{#endref\}\}", re.DOTALL)
# mdBook's include, which pulls one file into another at build time. Left
# unexpanded it shows as a directive standing where the content should be.
INCLUDE_RE = re.compile(r"\{\{#(?:rustdoc_)?include\s+([^}\s]+)\s*\}\}")
# Link and image targets together, for making a file's own relative paths
# absolute before it is pasted somewhere else.
TARGET_RE = re.compile(r"(!?\[[^\]]*\]\()([^)\s]+)(\s+\"[^\"]*\")?\)")
LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)(\s+\"[^\"]*\")?\)")
URL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


# Markdown allows raw HTML, and a terminal renderer prints it verbatim --
# so a document using it for images, badges or collapsible sections shows
# tag soup where the content should be. These are reduced to what they
# were standing for. Code is exempt: HTML inside a fence is the subject,
# not decoration.
FENCE_RE = re.compile(r"(^```.*?^```|^~~~.*?^~~~|`[^`\n]*`)", re.DOTALL | re.MULTILINE)
HTML_IMG_RE = re.compile(r"<img\b[^>]*?>", re.IGNORECASE)
HTML_ALT_RE = re.compile(r"""\balt\s*=\s*["']([^"']*)["']""", re.IGNORECASE)
HTML_SRC_RE = re.compile(r"""\bsrc\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
HTML_A_RE = re.compile(
    r"""<a\b[^>]*?\bhref\s*=\s*["']([^"']+)["'][^>]*?>(.*?)</a\s*>""",
    re.IGNORECASE | re.DOTALL,
)
HTML_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
HTML_TAG_RE = re.compile(r"</?(?:details|summary|div|span|p|b|strong|i|em|u|small|sup|sub|figure|figcaption|center)\b[^>]*?>", re.IGNORECASE)


def tidy_html(text):
    def strip(chunk):
        # An image written as HTML becomes a Markdown image, so it is drawn
        # rather than described -- which is what the author meant by it.
        def img(m):
            src = HTML_SRC_RE.search(m.group(0))
            if not src:
                return ""
            alt = HTML_ALT_RE.search(m.group(0))
            return "![{}]({})".format(alt.group(1) if alt else "", src.group(1))
        chunk = HTML_IMG_RE.sub(img, chunk)
        chunk = HTML_A_RE.sub(lambda m: "[{}]({})".format(m.group(2).strip(), m.group(1)), chunk)
        chunk = HTML_BR_RE.sub("\n", chunk)
        chunk = HTML_TAG_RE.sub("", chunk)
        return chunk

    out = []
    for i, part in enumerate(FENCE_RE.split(text)):
        # Odd indices are the code the pattern captured; leave them be.
        out.append(part if i % 2 else strip(part))
    return "".join(out)


def absolutize(text, base):
    """Resolve a chunk's relative targets against its own directory, so it
    still points where it meant to once inlined elsewhere."""
    def fix(m):
        head, target, title = m.group(1), m.group(2), m.group(3) or ""
        if URL_RE.match(target) or target.startswith("#"):
            return m.group(0)
        path = target.split("#", 1)[0]
        if not path:
            return m.group(0)
        return "{}{}{})".format(head, os.path.realpath(os.path.join(base, path)), title)
    return TARGET_RE.sub(fix, text)


def expand_includes(text, base, depth=0):
    """Inline what mdBook's preprocessor would have. Bounded, because a file
    including itself is a loop and not worth chasing."""
    if depth > 4:
        return text

    def repl(m):
        spec = m.group(1)
        path, _, rng = spec.partition(":")
        target = os.path.realpath(os.path.join(base, path))
        try:
            with open(target, encoding="utf-8") as fh:
                content = fh.read()
        except OSError:
            # Missing or unreadable: leave the directive visible rather than
            # quietly dropping the fact that something belongs here.
            return m.group(0)
        if rng:
            lines = content.split("\n")
            bits = rng.split(":")
            try:
                start = int(bits[0]) if bits[0] else 1
                end = int(bits[1]) if len(bits) > 1 and bits[1] else len(lines)
                content = "\n".join(lines[start - 1:end])
            except ValueError:
                pass  # a named anchor rather than line numbers: take it whole
        content = expand_includes(content, os.path.dirname(target), depth + 1)
        return absolutize(content, os.path.dirname(target))

    return INCLUDE_RE.sub(repl, text)


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
        return "![{}]({}{})".format(alt, path, title)

    def fix_link(m):
        label, target, title = m.group(1), m.group(2), m.group(3) or ""
        path = local_path(target)
        if path is None:
            return m.group(0)
        links.append({"label": label, "path": path})
        uri = "{}://{}{}".format(scheme, instance, quote(path))
        return "[{}]({}{})".format(label, uri, title)

    text = expand_includes(text, srcdir)
    if os.environ.get("MDNAV_HTML", "tidy") != "raw":
        text = tidy_html(text)
    # Rewritten into ordinary Markdown links first, so the same handling
    # applies to them as to anything else.
    text = REF_RE.sub(lambda m: "[{}]({})".format(m.group(1), m.group(1)), text)
    text = IMAGE_RE.sub(fix_image, text)
    text = LINK_RE.sub(fix_link, text)

    with open(out_md, "w", encoding="utf-8") as f:
        f.write(text)
    with open(out_links, "w", encoding="utf-8") as f:
        json.dump(links, f)


if __name__ == "__main__":
    main()
