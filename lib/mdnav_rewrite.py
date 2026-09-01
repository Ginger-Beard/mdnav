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
# A link written as a name, with the destination given once further down:
# [text][name], or [text][] where the text is the name. The shortcut form,
# a bare [name], is deliberately not read as a link -- it cannot be told
# apart from ordinary brackets, and "[[21]]" is a citation, not a target.
REFDEF_RE = re.compile(
    r"""^[ ]{0,3}\[([^\]]+)\]:[ \t]*<?([^\s>]+)>?[ \t]*((?:"[^"]*"|'[^']*'|\([^)]*\)))?[ \t]*$""",
    re.MULTILINE)
# A bare URL in angle brackets. Only looked for inside a table, where a
# renderer that drops it leaves nothing behind to click.
AUTOLINK_RE = re.compile(r"<((?:https?|ftp|mailto):[^>\s]+)>")
REFLINK_RE = re.compile(
    r"(?<!!)(!?)\[((?:[^\[\]]|\[[^\[\]]*\])*)\]\[([^\]]*)\]")
HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)
# What a heading is called once it is a link target: lowercased, stripped of
# anything that is not a word, and spaces hyphenated. Both GitHub and mdBook
# spell it this way, and both hyphenate each space rather than a run of them
# -- so a heading punctuated between two words ("A -- B", once the dash is
# stripped) leaves two spaces and gets two hyphens. Collapsing them here
# would name every such heading differently from the document that links to
# it.
def heading_text(text):
    """A heading with its markup taken off: the words a renderer will draw.

    Both halves of an anchor need this. The name is built from it, as
    GitHub builds one from the rendered heading rather than the written
    one; and the jump looks for it in the rendered buffer, where the
    backticks and asterisks are long gone. Keeping the written form here
    made a link that resolved -- so it looked like a link -- and then
    landed nowhere, because the line it was looking for did not exist.
    """
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\*\*?([^*]*)\*?\*", r"\1", text)
    # Underscores only where they wrap a word, so snake_case survives.
    text = re.sub(r"(?<!\w)_{1,2}([^_]+)_{1,2}(?!\w)", r"\1", text)
    text = re.sub(r"~~([^~]*)~~", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return text.strip()


def anchor_slug(text):
    text = heading_text(text).lower()
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


def expand_refstyle(text):
    """Turn [text][name] into the inline link it stands for.

    Everything downstream reads inline links, so a reference link is
    invisible to all of it: not registered, not followable, and not
    restorable in a table cell. Rewriting it here is enough to make it a
    link like any other. A name with no definition is left as it was
    written, since it is not a link either.
    """
    definitions = {}
    for m in REFDEF_RE.finditer(text):
        definitions.setdefault(m.group(1).strip().lower(), m.group(2))
    if not definitions:
        return text

    def fix(m):
        bang, label, name = m.group(1), m.group(2), m.group(3)
        key = (name.strip() or label.strip()).lower()
        target = definitions.get(key)
        if not target:
            return m.group(0)
        return "{}[{}]({})".format(bang, label, target)

    return outside_code(text, lambda chunk, at: REFLINK_RE.sub(fix, chunk))


LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")


def indented_ranges(text):
    """Ranges of the code blocks written by indentation rather than fences.

    Four spaces mean code after a blank line and ordinary text after a list
    item, where they mean the item continues. Told apart by what comes
    before: only a run that follows a blank line, and whose last non-blank
    predecessor is neither indented nor a list item, is read as code. Where
    that is unclear the run is left as text, which keeps a link in a deeply
    nested list working -- the commoner thing by far.
    """
    lines = text.split("\n")
    offsets = []
    pos = 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1

    out = []
    index = 0
    previous = None
    while index < len(lines):
        line = lines[index]
        indented = line.startswith("    ") or line.startswith("\t")
        after_blank = index == 0 or not lines[index - 1].strip()
        opens = previous is None or (
            not previous[:1].isspace() and not LIST_ITEM_RE.match(previous))
        if indented and after_blank and opens:
            start = index
            last = index
            while index < len(lines):
                if lines[index].startswith("    ") or lines[index].startswith("\t"):
                    last = index
                elif lines[index].strip():
                    break
                index += 1
            out.append((offsets[start], offsets[last] + len(lines[last])))
            continue
        if line.strip():
            previous = line
        index += 1
    return out


def code_ranges(text):
    """Everywhere a link is being shown rather than offered."""
    spans = [m.span() for m in FENCE_RE.finditer(text)]
    spans.extend(indented_ranges(text))
    spans.sort()
    merged = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append([start, end])
    return [(a, b) for a, b in merged]


def outside_code(text, transform):
    """Rewrite everything except code, and say where each piece began.

    A link inside a fence or a code span is a link being shown, not a link
    being offered: the document is talking about the markup. Rewritten, it
    is registered as somewhere to go, drawn with a target the author never
    typed, and -- in a table cell -- risks having a real link fastened onto
    literal text.

    `transform(chunk, offset)` gets each non-code piece and its position in
    the whole, so a rewrite can still tell where in the document it is.
    """
    out = []
    at = 0
    for start, end in code_ranges(text):
        if start > at:
            out.append(transform(text[at:start], at))
        out.append(text[start:end])
        at = end
    if at < len(text):
        out.append(transform(text[at:], at))
    return "".join(out)


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
    return outside_code(text, lambda chunk, at: SPACED_RE.sub(fix, chunk))


# The delimiter row that makes the line above it a table header, and so
# makes a table a table.
TABLE_DELIM_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$")


def table_spans(text):
    """Character ranges of each table, in the order they are written.

    A link inside a table has to be matched against the right table once
    rendered, and a table is identified by its position among the others:
    the first table written is the first table drawn.
    """
    lines = text.split("\n")
    offsets = []
    pos = 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1
    spans = []
    index = 0
    while index < len(lines):
        head, delim = lines[index], lines[index + 1] if index + 1 < len(lines) else ""
        if "|" in head and "|" in delim and TABLE_DELIM_RE.match(delim):
            end = index + 2
            while end < len(lines) and lines[end].strip() and "|" in lines[end]:
                end += 1
            spans.append((offsets[index], offsets[end - 1] + len(lines[end - 1])))
            index = end
        else:
            index += 1
    return spans


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
    srcfile = os.path.realpath(src)
    srcdir = os.path.dirname(srcfile)
    text = open(src, encoding="utf-8").read()
    links = []
    # Where each anchor points, by the text of the heading that defines it.
    anchors = {anchor_slug(m.group(2)): heading_text(m.group(2))
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

    table_ranges = []

    def in_table(at):
        """Index of the table this link sits in, or None if it sits in none."""
        for number, (start, end) in enumerate(table_ranges):
            if start <= at < end:
                return number
        return None

    def fix_link(m, at):
        label, title = m.group("label"), m.group("title") or ""
        target = destination(m)
        table = in_table(at)
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
            if not scheme:
                links.append({"label": label, "path": target})
                # Nothing is listening for a click, but an anchor is still a
                # link, and it is the only kind that was being dropped to
                # text -- so a reader saw some links working and others
                # silently not, and a resolved anchor looked exactly like
                # one that named nothing.
                #
                # A place in this document, written out, is this document
                # and the place in it: the same form a link into another
                # file's section takes, and a target that still exists once
                # mdnav has gone. Left bare, "#slug" would be resolved
                # against the copy being rendered and point into a temp
                # directory that is deleted on the way out.
                return "[{}]({}{})".format(
                    label, as_dest(srcfile + "#" + slug), title)
            uri = "{}://{}/{}".format(scheme, instance, quote(target))
            links.append({"label": label, "path": target, "uri": uri,
                          "text": heading_text(label), "table": table})
            return "[{}]({}{})".format(label, uri, title)
        path = local_path(target)
        if path is None:
            if URL_RE.match(target):
                # Somewhere outside the document. It is left exactly as
                # written, for the renderer and the desktop to deal with
                # between them -- but inside a table the renderer drops it,
                # so it is recorded there in case it has to be put back.
                if table is not None and scheme:
                    links.append({"label": label, "path": target,
                                  "uri": target, "text": heading_text(label),
                                  "table": table, "external": True})
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
        if not scheme:
            links.append({"label": label, "path": path})
            # Nothing is listening for a click, so the path itself is the
            # honest target -- the scheme would only show as noise.
            return "[{}]({}{})".format(label, as_dest(path), title)
        uri = "{}://{}{}".format(scheme, instance, quote(path))
        links.append({"label": label, "path": path, "uri": uri,
                      "text": heading_text(label), "table": table})
        return "[{}]({}{})".format(label, uri, title)

    text = expand_includes(text, srcdir)
    if os.environ.get("MDNAV_HTML", "tidy") != "raw":
        text = tidy_html(text)
    # Rewritten into ordinary Markdown links first, so the same handling
    # applies to them as to anything else.
    text = REF_RE.sub(lambda m: "[{}]({})".format(m.group(1), m.group(1)), text)
    text = expand_refstyle(text)
    text = bracket_spaced(text, srcdir)
    text = outside_code(text, lambda chunk, at: IMAGE_RE.sub(fix_image, chunk))
    # Worked out on the text the links are about to be read from, so the
    # offsets are the ones fix_link will be given.
    table_ranges[:] = table_spans(text)
    text = outside_code(
        text,
        lambda chunk, at: LINK_RE.sub(lambda m: fix_link(m, at + m.start()), chunk))
    # A bare <url> is not written as a link and never reaches fix_link, but
    # in a table it is dropped like any other, so it is recorded too.
    if scheme:
        # Worked out again: rewriting the links above changed the length of
        # everything after the first one, so the earlier ranges no longer
        # say where the tables are.
        for number, (start, end) in enumerate(table_spans(text)):
            for m in AUTOLINK_RE.finditer(text, start, end):
                url = m.group(1)
                links.append({"label": url, "path": url, "uri": url,
                              "text": url, "table": number, "external": True})

    with open(out_md, "w", encoding="utf-8") as f:
        f.write(text)
    with open(out_links, "w", encoding="utf-8") as f:
        json.dump(links, f)
    with open(out_links + ".anchors", "w", encoding="utf-8") as f:
        json.dump(anchors, f)


if __name__ == "__main__":
    main()
