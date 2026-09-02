#!/usr/bin/env python3
"""What the Python helpers are supposed to do.

Every case here is one that was got wrong at some point: a link that
disappeared, an anchor that scrolled to the wrong line, an image measured
as one row when it drew ten. They are written down so that getting them
wrong again is noticed here rather than by a reader.

usage: python3 tests/test_helpers.py
"""

import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "lib")


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(LIB, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rewrite = load("mdnav_rewrite")
spans = load("mdnav_spans")
links = load("mdnav_links")
tablelinks = load("mdnav_tablelinks")

FAILURES = []
COUNT = 0


def check(name, got, want):
    global COUNT
    COUNT += 1
    if got != want:
        FAILURES.append("{}\n      got:  {!r}\n      want: {!r}".format(name, got, want))


def group(title):
    print("  " + title)


# --- naming an anchor -------------------------------------------------
# GitHub and mdBook hyphenate each space rather than a run of them, so a
# heading punctuated between two words gets two hyphens, not one.
group("anchor names")
check("em dash keeps both hyphens",
      rewrite.anchor_slug("ER-074 — Encryption of Data in Transit"),
      "er-074--encryption-of-data-in-transit")
check("plain heading", rewrite.anchor_slug("Getting Started"), "getting-started")
check("parenthesised", rewrite.anchor_slug("Setup (Linux) — Notes"), "setup-linux--notes")
# Markup is taken off before naming, because a renderer draws the words
# without it and the name has to match what a reader sees.
check("code span", rewrite.anchor_slug("The `--ansi` flag"), "the---ansi-flag")
check("bold", rewrite.anchor_slug("**Bold** heading"), "bold-heading")
check("underscore emphasis", rewrite.anchor_slug("_Italic_ heading"), "italic-heading")
check("snake_case survives", rewrite.anchor_slug("read_key_wait explained"),
      "read_key_wait-explained")
check("heading text drops markup", rewrite.heading_text("The `--ansi` flag"),
      "The --ansi flag")


# --- measuring a line -------------------------------------------------
group("row counts")
with tempfile.TemporaryDirectory() as tmp:
    buf = os.path.join(tmp, "buf")
    # A sixel says how tall it is in its raster attributes; saying one row
    # for something that draws nine leaves the pager scrolling short.
    io.open(buf, "wb").write(b'before\n\x1bP9;1;0q"1;1;60;180\x1b\\\nafter\n')
    check("sixel measured from its own geometry",
          subprocess.run([sys.executable, os.path.join(LIB, "mdnav_spans.py"), buf, "80", "20"],
                         capture_output=True).stdout.decode().split(),
          ["1", "9", "1", "1"])
    io.open(buf, "wb").write(b"before\n\x1b_Ga=T,f=100,r=7,c=20;AAAA\x1b\\\nafter\n")
    check("kitty says its rows outright",
          subprocess.run([sys.executable, os.path.join(LIB, "mdnav_spans.py"), buf, "80", "20"],
                         capture_output=True).stdout.decode().split(),
          ["1", "7", "1", "1"])


# --- where a link points ----------------------------------------------
group("link resolution")
with tempfile.TemporaryDirectory() as tmp:
    os.makedirs(os.path.join(tmp, "with readme"))
    os.makedirs(os.path.join(tmp, "plain", "nested"))
    io.open(os.path.join(tmp, "with readme", "README.md"), "w").write("# S\n")
    io.open(os.path.join(tmp, "plain", "alpha.md"), "w").write("# A\n")
    io.open(os.path.join(tmp, "spaced name.md"), "w").write("# S\n")

    def found(target, base=None):
        answer = rewrite.find_target(target, base or tmp)
        return os.path.relpath(answer, tmp) if answer else None

    # A directory is the page inside it, and a listing when there is none.
    check("directory means its README", found("with readme"), "with readme/README.md")
    check("trailing slash too", found("with readme/"), "with readme/README.md")
    check("directory without one stands for itself", found("plain"), "plain")
    check("nothing there", found("no-such.md"), None)
    # A path with a space is ordinary on a desktop, in three spellings.
    check("literal space", found("spaced name.md"), "spaced name.md")
    check("percent-encoded", found("spaced%20name.md"), "spaced name.md")
    check("bracketed is the same path", found("plain/alpha.md"), "plain/alpha.md")


# --- reading a whole document -----------------------------------------
group("rewriting")


def rewritten(text, scheme="mdnav", name="doc.md"):
    tmp = tempfile.mkdtemp()
    try:
        src = os.path.join(tmp, name)
        io.open(src, "w").write(text)
        io.open(os.path.join(tmp, "other.md"), "w").write("# Other\n\n## Section\n")
        out = os.path.join(tmp, "out.md")
        jsonf = os.path.join(tmp, "links.json")
        subprocess.run([sys.executable, os.path.join(LIB, "mdnav_rewrite.py"),
                        src, out, jsonf, scheme], capture_output=True)
        import json
        return io.open(out).read(), json.load(io.open(jsonf))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


text, registered = rewritten("See [a](other.md) and [b](other.md#section).\n")
check("a link is registered", len(registered), 2)
check("a cross-file anchor keeps its place",
      registered[1]["path"].endswith("other.md#section"), True)

# A link being shown rather than offered is left alone.
text, registered = rewritten(
    "Inline `[z](other.md)` and\n\n```\n[q](other.md)\n```\n\n[real](other.md)\n")
check("only the real link is registered", [r["label"] for r in registered], ["real"])
check("the code span is untouched", "`[z](other.md)`" in text, True)
check("the fence is untouched", "[q](other.md)" in text, True)

# Reference-style links are resolved against their definition.
text, registered = rewritten("[text][ref]\n\n[ref]: other.md\n")
check("reference-style link resolves", [r["label"] for r in registered], ["text"])

# A citation carries the item it names, so the jump lands on the item.
text, registered = rewritten("Body [[21]](#refs)\n\n## Refs\n\n1. one\n")
check("citation keeps its item", registered[0]["path"], "#refs|21")

# Every table is numbered, so a restored link goes back into its own.
text, registered = rewritten(
    "| a | b |\n|---|---|\n| x | [one](other.md) |\n\ntext\n\n"
    "| a | b |\n|---|---|\n| y | [two](other.md) |\n")
check("links know which table they were in",
      [r.get("table") for r in registered], [0, 1])


# --- finding the tables in rendered output ----------------------------
group("table regions")
lines = ["", "────────", " head ", "────────", " row ", "────────", "", "after"]
check("a table is found", tablelinks.table_regions(lines), [(1, 5)])
# A rule with nothing under it is a box in a code block, not a table;
# counted as one it shifts every table after it.
check("a lone rule is not a table",
      tablelinks.table_regions(["", "────────", "", "text"]), [])


# --- what to do with a file ------------------------------------------
# Nothing here trusts a name: opening and running are the same gesture on
# every desktop, so what is handed over has to be identified by content.
group("deciding what a file is")
kind = load("mdnav_kind")
with tempfile.TemporaryDirectory() as tmp:
    def make(name, data):
        path = os.path.join(tmp, name)
        io.open(path, "wb").write(data)
        return path

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
    check("a picture is handed over", kind.kind(make("a.png", png)), "desktop")
    check("even with no extension", kind.kind(make("nameless", png)), "desktop")
    check("a picture calling itself a document is still a picture",
          kind.kind(make("lying.pdf", png)), "desktop")
    # The one that matters: a program renamed to look harmless.
    check("a program calling itself a document is refused",
          kind.kind(make("evil.pdf", b"\x7fELF\x02\x01\x01" + b"\x00" * 40)),
          "refuse")
    check("a program is refused",
          kind.kind(make("thing", b"MZ\x90\x00\x03" + b"\x00" * 40)), "refuse")
    # Text is shown here, where it cannot do anything, whatever it is called.
    check("a script is shown, not run",
          kind.kind(make("go.sh", b"#!/bin/sh\nrm -rf /\n")), "text")
    check("a batch file is shown, not run",
          kind.kind(make("go.bat", b"echo hello\r\n")), "text")
    check("a desktop entry is shown, not run",
          kind.kind(make("x.desktop", b"[Desktop Entry]\nExec=rm\n")), "text")
    check("a file with no extension is read to find out",
          kind.kind(make("Dockerfile", b"FROM alpine\n")), "text")
    check("markdown is a document", kind.kind(make("a.md", b"# hi\n")), "markdown")
    # A macOS bundle is a directory that is a program.
    os.makedirs(os.path.join(tmp, "Thing.app"))
    check("a bundle is refused", kind.kind(os.path.join(tmp, "Thing.app")), "refuse")
    os.makedirs(os.path.join(tmp, "plain-folder"))
    check("an ordinary folder is not",
          kind.kind(os.path.join(tmp, "plain-folder")), "markdown")


# --- showing a file as a page ----------------------------------------
group("files shown as pages")
with tempfile.TemporaryDirectory() as tmp:
    src = os.path.join(tmp, "sample.py")
    io.open(src, "w").write("import os\n" + "x = 1\n" * 3 + "y = " + "9" * 300 + "\n")
    page = rewrite.as_code_page(src)
    check("it is fenced as what it is", "```python" in page, True)
    check("it carries no numbers of its own", "  1  import os" in page, False)
    check("the name is the heading", page.startswith("# sample.py"), True)

    # The numbers go on after rendering, and have to land on the file's own
    # lines -- including one far too long for the window, which the terminal
    # wraps but which is still one line.
    buf = os.path.join(tmp, "buf")
    io.open(buf, "wb").write(b"\n\nheading\n\n" + b"\n".join(
        [b"import os", b"x = 1", b"x = 1", b"x = 1", b"y = " + b"9" * 300]) + b"\n\n")
    subprocess.run([sys.executable, os.path.join(LIB, "mdnav_number.py"), buf, "5"],
                   capture_output=True)
    numbered = io.open(buf, "rb").read().decode()
    check("the first line is numbered 1", "\x1b[2m1\x1b[22m  import os" in numbered, True)
    check("the long line is numbered once", numbered.count("\x1b[2m5\x1b[22m"), 1)
    check("the heading above is left alone", "\x1b[2m" in numbered.split("heading")[0], False)


# --- summary ----------------------------------------------------------
print()
if FAILURES:
    print("  %d of %d failed" % (len(FAILURES), COUNT))
    for failure in FAILURES:
        print("    " + failure)
    sys.exit(1)
print("  %d checks passed" % COUNT)
