# mdnav

`mdcat`, with links you can click.

[mdcat](https://github.com/swsnr/mdcat) renders Markdown in the terminal
beautifully — including real images, via sixel or the kitty protocol. What it
cannot do is let you *follow* a link to another local file: activating one hands
it to your desktop, which opens it in some other application, in some other
window.

mdnav keeps you where you are. Click a link to another Markdown file and it
renders in the same pane, with a back stack. Images still work,
scrolling still works, and documents of any length work — none of which is true
of the obvious approaches (see [Why not just…](#why-not-just)).

```
mdnav README.md
```

```
up/down, k/j, wheel    scroll a line
space/PgDn, u/PgUp     scroll a page
g / G                  top / bottom
ctrl+click             follow a link
l                      list links, pick one by number
b, backspace           back to the previous file
r                      reload
q                      quit
```

It is a pager: opens at the top, scrolls both ways, no flags.

### Images are sliced

An image would normally make that impossible. A sixel image is a single
escape sequence the terminal rasterises whole, routinely tens of rows
tall, and nothing above the terminal can say how tall it came out or draw
part of it. A pager cannot lay out what it cannot measure, which is also
why `less` mangles mdcat's output: it counts a 79-row image as one line.

So mdnav cuts each image into strips exactly one text row tall, one sixel
escape each, before rendering. Every line in the buffer is then exactly
one screen row. Layout is arithmetic again, and a half-scrolled image is
just the strips that fall inside the window.

This needs ImageMagick (`convert`) and a sixel terminal. Without either,
images are left whole and drawn by mdcat -- everything still works, but a
tall image jumps into view rather than scrolling.

Strips are cached under `~/.cache/mdnav`, keyed by the image, its
modification time, and the width it was rendered for. Slicing a tall image
takes about a second; afterwards it is immediate.

## How it works

The trick is that the *terminal* has to tell a *running program* that you
clicked something, and terminals have no way to do that. So mdnav borrows the
one channel that does cross that gap: a URL scheme.

1. Before rendering, mdnav rewrites local links in a temp copy of the document
   from `./OTHER.md` to `mdnav:///abs/path/OTHER.md`.
2. mdcat renders that copy and emits each link as an OSC 8 hyperlink — the
   terminal now owns the hit-testing, at any scroll position.
3. Clicking hands `mdnav://…` to the desktop, which routes it to `mdnav-open`.
4. `mdnav-open` writes the path into a FIFO that the running mdnav is reading,
   and mdnav re-renders in place.

If no mdnav is running, `mdnav-open` opens the file the ordinary way instead, so
a click never silently does nothing.

## Platform support

**Only WSL2 has actually been tested** — Ubuntu 24.04 under Windows Terminal
1.24, with mdcat 2.15. Everything else is written from the specs and reasoning
below, and has never been run. Reports very welcome.

| | clicking | images | tested |
|---|---|---|---|
| WSL2 + Windows Terminal | yes, with a confirmation dialog | yes, sixel | **yes** |
| Linux, OSC 8 terminal (kitty, WezTerm, foot, Ghostty…) | should work, via XDG | should work | no |
| macOS (iTerm2, kitty, WezTerm, Ghostty) | should work, via Launch Services | should work | no |
| Terminal without OSC 8 | no — use `l` to pick links by number | unchanged | no |

On **Linux** the scheme is claimed with an XDG `.desktop` entry; on **macOS**
by building a small AppleScript app bundle in `~/Applications` and handing it
to Launch Services. Both follow the documented mechanism, neither has been
exercised.

macOS ships bash 3.2, which mdnav works around, so no Homebrew bash is needed.

**On WSL**, clicks are handled by Windows rather than Linux, so the scheme is
registered under `HKCU` and dispatched back through `wsl.exe`. Windows Terminal
shows a *"This link may lead to an unsafe location"* confirmation for any
non-web scheme, and offers no setting to suppress it — so following a link there
costs an extra click. This is the price of the only mechanism that survives the
round trip; see below.

## Why not just…

Things that look like they should work, and don't:

- **`mdcat`'s own links.** mdcat renders local links as `file://<hostname>/path`
  — correct per the OSC 8 spec, so that links resolve over SSH. Windows cannot
  open that form, so on WSL every link fails with *"This link type is currently
  not supported."* mdnav's custom scheme passes through mdcat untouched, which
  `file://` does not.
- **Registering `mdcat` as the `.md` handler.** Works, but every click opens a
  new window — the thing you were trying to avoid.
- **Mouse tracking (`\e[?1000h`) and mapping clicks to rows.** The terminal
  does forward the clicks. But you cannot know which row a link landed on:
  sixel images advance the cursor by an amount that lives inside the escape
  sequence, not in the text, so counting lines cannot see it. Querying the
  cursor afterwards (`\e[6n`) gives you an exact answer for the *last screenful*
  only — for anything longer, the rest has already scrolled off. And enabling
  mouse mode takes over the scroll wheel, so you cannot scroll to reach it.

## Limitations

- One reader per user: a second `mdnav` takes over the FIFO, and clicks go to
  the newest one.
- Reference-style links (`[a][b]` with a separate definition) are not rewritten;
  inline `[a](b)` is.
- Links to non-Markdown files are handed to the desktop rather than rendered.
