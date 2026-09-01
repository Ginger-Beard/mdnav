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
from urllib.parse import quote, unquote

# A target that resolves to nothing is shown as plain text rather than as
# a link, which is right -- but it makes a link the tool cannot handle look
# exactly like a link the document got wrong, and the difference is only
# findable by bisecting the file. Set MDNAV_DEBUG to a path to be told
# instead. Never written to stderr: the pager owns the screen, and a line
# sent there lands in the middle of the document.
DEBUG = os.environ.get("MDNAV_DEBUG", "")
SOURCE = ""


def note(fmt, *args):
    """A line in the same trace file the pager writes, appended rather than
    printed: the pager owns the screen, and a line sent to stderr lands in
    the middle of the document. Prefixed, so it can be picked out of the
    shell trace around it."""
    if not DEBUG:
        return
    try:
        with open(DEBUG, "a", encoding="utf-8") as fh:
            fh.write("mdnav: {}: {}\n".format(
                os.path.basename(SOURCE) or "?", fmt.format(*args)))
    except OSError:
        pass


# Where a link points, in either of the two spellings CommonMark gives it:
# bracketed, which may contain spaces, or a bare run that may not. A path
# with a space in it is ordinary on a desktop, and only the first spelling
# can carry one.
DEST = r"(?:<(?P<angle>[^<>\n]*)>|(?P<bare>[^)\s]+))"
TITLE = r"(?P<title>\s+\"[^\"]*\")?"


def destination(m):
    """The target of whichever spelling matched."""
    angle = m.group("angle")
    return angle if angle is not None else m.group("bare")


def as_dest(path):
    """A path written so that reading it back gives the path again. Bare, a
    space ends the destination and the rest becomes a title that is not
    one."""
    if not re.search(r"\s", path):
        return path
    if "<" not in path and ">" not in path:
        return "<{}>".format(path)
    return quote(path)


IMAGE_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\(" + DEST + TITLE + r"\)")
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
# A label can hold brackets of its own -- [[21]](#ref) is a reference
# marker written as a link -- so one level of nesting is allowed for.
TARGET_RE = re.compile(
    r"(?P<head>!?\[(?:[^\[\]]|\[[^\[\]]*\])*\]\()" + DEST + TITLE + r"\)")
LINK_RE = re.compile(
    r"(?<!!)\[(?P<label>(?:[^\[\]]|\[[^\[\]]*\])*)\]\(" + DEST + TITLE + r"\)")
URL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)
# What a heading is called once it is a link target: lowercased, stripped of
# anything that is not a word, and spaces hyphenated. Both GitHub and mdBook
# spell it this way, and both hyphenate each space rather than a run of them
# -- so a heading punctuated between two words ("A -- B", once the dash is
# stripped) leaves two spaces and gets two hyphens. Collapsing them here
# would name every such heading differently from the document that links to
# it.
def anchor_slug(text):
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\*\*?([^*]*)\*?\*", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    return re.sub(r"\s", "-", text)


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


def source_variants(path):
    """The source file a built path corresponds to.

    Documents written for a site link to what the build produces --
    index.html for a directory, foo.html for foo.md -- and those names do
    not exist in the source anyone reads in a terminal.
    """
    yield path
    base = path[:-len(".html")] if path.endswith(".html") else None
    if path.endswith("/index.html") or path == "index.html":
        directory = path[:-len("index.html")]
        yield directory + "README.md"
        yield directory + "index.md"
    elif base:
        yield base + ".md"
        yield base + "/README.md"
    if path.endswith("/"):
        yield path + "README.md"
        yield path + "index.md"


# A bare destination stops at the first space, so a path with a space in it
# is not a destination at all and the whole construct is not a link -- by
# the spec, correctly so. It is also what every file manager puts on the
# clipboard, so documents are full of them. Accepted here on one condition:
# it has to name a file that exists. Without that condition, any
# parenthesised prose after a bracketed word would be read as a path.
SPACED_RE = re.compile(
    r"(?P<head>!?\[(?:[^\[\]]|\[[^\[\]]*\])*\]\()(?P<inner>[^)<>\n]*\s[^)<>\n]*)\)")


def bracket_spaced(text, *bases):
    """Give a spaced destination that names a real file the one spelling
    that can carry it, so everything downstream sees an ordinary link."""
    def fix(m):
        head, inner = m.group("head"), m.group("inner")
        if inner.startswith("#") or URL_RE.match(inner.strip()):
            return m.group(0)
        # A destination the parser can already read, followed by a title.
        first = inner.split()[0] if inner.split() else ""
        if first and find_target(first.split("#", 1)[0], *bases):
            return m.group(0)
        options = [(inner.strip(), "")]
        split = re.match(r'^(.*?)(\s+"[^"]*")$', inner)
        if split:
            options.append((split.group(1).strip(), split.group(2)))
        for candidate, title in options:
            if candidate and find_target(candidate.split("#", 1)[0], *bases):
                return "{}<{}>{})".format(head, candidate, title)
        note("target {!r}: has a space and names nothing", inner)
        return m.group(0)
    return SPACED_RE.sub(fix, text)


def spellings(target):
    """The same target as the document wrote it, and as the filesystem
    spells it. An editor inserting a link percent-encodes the spaces in a
    path; the file on disk still has spaces in its name."""
    yield target
    decoded = unquote(target)
    if decoded != target:
        yield decoded


def find_target(target, *bases):
    """Where a relative path actually points.

    A file pulled in from elsewhere carries paths written for wherever it
    was meant to sit, and they routinely climb past the top of the tree --
    resolved literally they become a path outside it that exists nowhere.
    Try each plausible base, then look for the tail of the path in the
    directories above the document, and give up rather than inventing an
    answer that happens to be a valid string."""
    for spelling in spellings(target):
        found = resolve_one(spelling, bases)
        if found is not None:
            return found
    return None


def resolve_one(target, bases):
    for base in bases:
        if not base:
            continue
        for variant in source_variants(target):
            candidate = os.path.realpath(os.path.join(base, variant))
            if os.path.exists(candidate):
                return candidate
        # A directory stands for the page inside it.
        candidate = os.path.realpath(os.path.join(base, target))
        if os.path.isdir(candidate):
            for name in ("README.md", "index.md"):
                inner = os.path.join(candidate, name)
                if os.path.exists(inner):
                    return inner

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
        head, title = m.group("head"), m.group("title") or ""
        target = destination(m)
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
        # The place in the file survives the file being renamed absolute.
        # Dropped here, an included link would open its target at the top
        # while the same link outside an include lands on the section.
        frag = target.partition("#")[2]
        if frag:
            found += "#" + frag
        return "{}{}{})".format(head, as_dest(found), title)
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
    global SOURCE
    src, out_md, out_links, scheme = sys.argv[1:5]
    SOURCE = src
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
    # The same anchors with their hyphens run together, for a document that
    # wrote one hyphen where the heading gives two. Nothing else resolves
    # such a target, but a reader that finds the heading anyway is worth
    # more than one that drops the link. Only consulted when the anchor as
    # written matches nothing, and only where the loose spelling names a
    # single heading.
    loose = {}
    for key in anchors:
        short = re.sub(r"-+", "-", key)
        if short != key:
            loose[short] = None if short in loose else key

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
        alt, title = m.group("alt"), m.group("title") or ""
        target = destination(m)
        path = local_path(target)
        if path is None:
            note("image {!r}: nothing there", target)
            return m.group(0)
        return "![{}]({}{})".format(alt, as_dest(path), title)

    def fix_link(m):
        label, title = m.group("label"), m.group("title") or ""
        target = destination(m)
        if target.startswith("#"):
            # A place in this same document. Followed here rather than
            # handed to the desktop, which can only read it as a file that
            # does not exist.
            slug = anchor_slug(target[1:])
            if slug not in anchors:
                slug = loose.get(re.sub(r"-+", "-", slug))
                if slug is None:
                    note("anchor {!r}: no heading of that name", target)
                    return label
            # A citation marker names an item, while the anchor names only
            # the section holding it -- Markdown has no anchor per item, so
            # documents point every citation at the same heading. The label
            # is the missing half: carry it along and land on the item.
            item = re.sub(r"[\[\]]", "", label).strip()
            target = "#" + slug
            if re.fullmatch(r"\d{1,4}", item):
                target += "|" + item
            links.append({"label": label, "path": target})
            if not scheme:
                return label
            uri = "{}://{}/{}".format(scheme, instance, quote(target))
            return "[{}]({}{})".format(label, uri, title)
        path = local_path(target)
        if path is None:
            if URL_RE.match(target):
                return m.group(0)
            note("link {!r}: nothing there", target)
            # A local target that resolves to nothing: shown as text, not as
            # a link. Left as a link, it would be resolved against the copy
            # being rendered and become a path into the temp directory --
            # which looks real, and is not.
            return label
        # A link into a section of another document: the file to open, and
        # the place in it. Both are carried, and the place is resolved when
        # that file is loaded, because the headings are its own and are not
        # known here.
        frag = target.partition("#")[2]
        if frag:
            path += "#" + anchor_slug(frag)
        links.append({"label": label, "path": path})
        if not scheme:
            # Nothing is listening for a click, so the path itself is the
            # honest target -- the scheme would only show as noise.
            return "[{}]({}{})".format(label, as_dest(path), title)
        uri = "{}://{}{}".format(scheme, instance, quote(path))
        return "[{}]({}{})".format(label, uri, title)

    text = expand_includes(text, srcdir)
    if os.environ.get("MDNAV_HTML", "tidy") != "raw":
        text = tidy_html(text)
    # Rewritten into ordinary Markdown links first, so the same handling
    # applies to them as to anything else.
    text = REF_RE.sub(lambda m: "[{}]({})".format(m.group(1), m.group(1)), text)
    text = bracket_spaced(text, srcdir)
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
