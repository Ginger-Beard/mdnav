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


# --- summary ----------------------------------------------------------
print()
if FAILURES:
    print("  %d of %d failed" % (len(FAILURES), COUNT))
    for failure in FAILURES:
        print("    " + failure)
    sys.exit(1)
print("  %d checks passed" % COUNT)
