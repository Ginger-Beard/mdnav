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
HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)
# What a heading is called once it is a link target: lowercased, stripped of
# anything that is not a word, and spaces hyphenated. Both GitHub and mdBook
# spell it this way.
def anchor_slug(text):
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\*\*?([^*]*)\*?\*", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    return re.sub(r"[\s]+", "-", text)


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
        # rather than described -- unless its alt is empty, which is how a
        # document says the image is decoration. Badges flanking a link are
        # the usual case, and drawing them buries the link between them.
        def img(m):
            src = HTML_SRC_RE.search(m.group(0))
            alt = HTML_ALT_RE.search(m.group(0))
            if not src or (alt and not alt.group(1).strip()):
                return ""
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


def find_target(target, *bases):
    """Where a relative path actually points.

    A file pulled in from elsewhere carries paths written for wherever it
    was meant to sit, and they routinely climb past the top of the tree --
    resolved literally they become a path outside it that exists nowhere.
    Try each plausible base, then look for the tail of the path in the
    directories above the document, and give up rather than inventing an
    answer that happens to be a valid string."""
    for base in bases:
        if not base:
            continue
        candidate = os.path.realpath(os.path.join(base, target))
        if os.path.exists(candidate):
            return candidate

    tail = target
    while tail.startswith("./") or tail.startswith("../"):
        tail = tail[2:] if tail.startswith("./") else tail[3:]
    if not tail:
        return None
    for base in bases:
        if not base:
            continue
        here = base
        for _ in range(8):
            candidate = os.path.join(here, tail)
            if os.path.exists(candidate):
                return os.path.realpath(candidate)
            parent = os.path.dirname(here)
            if parent == here:
                break
            here = parent
    return None


def absolutize(text, base, doc_dir=None):
    """Resolve a chunk's relative targets against its own directory, so it
    still points where it meant to once inlined elsewhere."""
    def fix(m):
        head, target, title = m.group(1), m.group(2), m.group(3) or ""
        if URL_RE.match(target) or target.startswith("#"):
            return m.group(0)
        path = target.split("#", 1)[0]
        if not path:
            return m.group(0)
        found = find_target(path, base, doc_dir)
        if found is None:
            # Leave it as written: a wrong absolute path is worse than an
            # unresolved relative one, which at least says what it meant.
            return m.group(0)
        return "{}{}{})".format(head, found, title)
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
        return absolutize(content, os.path.dirname(target), base)

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
    # Where each anchor points, by the text of the heading that defines it.
    anchors = {anchor_slug(m.group(2)): m.group(2).strip()
               for m in HEADING_RE.finditer(text)}

    def local_path(target):
        """Absolute path for a local target, or None if it isn't one."""
        if URL_RE.match(target) or target.startswith("#"):
            return None
        path = target.split("#", 1)[0]
        if not path:
            return None
        # Nothing there: leave the target as the document wrote it. An
        # absolute path to a file that does not exist only looks authoritative.
        return find_target(path, srcdir)

    def fix_image(m):
        alt, target, title = m.group(1), m.group(2), m.group(3) or ""
        path = local_path(target)
        if path is None:
            return m.group(0)
        return "![{}]({}{})".format(alt, path, title)

    def fix_link(m):
        label, target, title = m.group(1), m.group(2), m.group(3) or ""
        if target.startswith("#"):
            # A place in this same document. Followed here rather than
            # handed to the desktop, which can only read it as a file that
            # does not exist.
            slug = anchor_slug(target[1:])
            if slug not in anchors:
                return label
            links.append({"label": label, "path": "#" + slug})
            if not scheme:
                return label
            uri = "{}://{}/{}".format(scheme, instance, quote("#" + slug))
            return "[{}]({}{})".format(label, uri, title)
        path = local_path(target)
        if path is None:
            return m.group(0)
        links.append({"label": label, "path": path})
        if not scheme:
            # Nothing is listening for a click, so the path itself is the
            # honest target -- the scheme would only show as noise.
            return "[{}]({}{})".format(label, path, title)
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
    with open(out_links + ".anchors", "w", encoding="utf-8") as f:
        json.dump(anchors, f)


if __name__ == "__main__":
    main()
