# Working on mdnav

For anyone changing it. If you only want to *use* it, the
[README](../README.md) is the whole story.

## What is where

| | |
|---|---|
| `bin/mdnav` | the pager: the screen, the keys, the mouse, the back stack |
| `bin/mdnav-open` | what the desktop runs when an `mdnav://` link is clicked |
| `lib/mdnav_rewrite.py` | reads a document and rewrites its links; the largest piece |
| `lib/mdnav_links.py` | where each link sits on screen, once rendered |
| `lib/mdnav_spans.py` | how many rows each line will occupy |
| `lib/mdnav_anchor.py` | which line an anchor names |
| `lib/mdnav_slice.py` | cuts images into strips one row tall |
| `lib/mdnav_tablelinks.py` | puts back the links a renderer drops in tables |
| `lib/mdnav_search.py` | finds and marks matches |
| `lib/mdnav_keys.sh` | turns bytes from the terminal into key and mouse events |

The split is deliberate: the shell owns the screen and the state, and
Python does anything involving text, paths or arithmetic. So most
behaviour can be tested without a terminal at all.

## Tests

    python3 tests/test_helpers.py     # a second, needs nothing
    bash tests/test_pager.sh          # needs mdcat and a terminal

The first covers the Python. The second drives the real pager through a
pseudo-terminal, sending keys and mouse reports and reading the status
bar back, and skips rather than fails where there is no `mdcat`.

Both run on every push, along with `shellcheck`. See
[`.github/workflows/ci.yml`](../.github/workflows/ci.yml).

Every case in the tests is one that was got wrong at some point. When you
fix something, add the case that was wrong -- and check the test fails
with the fix taken out, because a test that cannot fail is worth nothing.

## Driving the pager by hand

`tests/drive.py` runs mdnav in a pseudo-terminal of a given size and
prints what it wrote. It is the only way to see what the pager does,
since it takes over the screen.

    python3 tests/drive.py 24 90 README.md '\e[<0;6;8M' '\e[<0;6;8m'

Keys are arguments. `\r` is return, `\e` an escape, so a click is an SGR
mouse report: `\e[<0;COL;ROWM` to press and `m` to release. To find out
which row and column a link is on, render the file and ask:

    python3 lib/mdnav_rewrite.py README.md /tmp/out.md /tmp/links.json mdnav
    mdcat --ansi --columns 90 /tmp/out.md > /tmp/buf.ansi
    python3 lib/mdnav_links.py /tmp/buf.ansi

which prints a line per link: buffer line, first column, last column,
target. Screen row is the buffer line plus one, when the view is at the
top.

## Tracing

`MDNAV_DEBUG=/tmp/mdnav.log` writes a shell trace, and with it the
decisions that are otherwise invisible: every link dropped and why,
whether images were left whole, and whether a document was rendered or
reused from earlier in the session.

    grep '^mdnav:' /tmp/mdnav.log

## Releasing

Change `VERSION=` in `bin/mdnav` and push. A push whose version has no
release yet gets one: the tests run, a tarball and its checksum are built,
and a release is published with the tag made for it. Every other push does
nothing, so there is no separate step to remember and no way to release a
version without the program agreeing what it is.

It is one workflow rather than two on purpose. Tagging from a workflow and
letting the tag set off a release does not work: a tag pushed with the
default token triggers nothing, by design, so the release would never
run.

## House style

Comments say *why*, not *what* -- the code already says what. Several of
the odder-looking decisions here are load-bearing and are commented as
such: an image is one indivisible escape, so it must be sliced before a
pager can measure it; a link is written to the terminal as its event
arrives, which is why a table cell has to carry its own; and paths are
resolved only once something is known to be there, because resolving one
walks every component of it.
