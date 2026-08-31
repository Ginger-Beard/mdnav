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
click   follow a link
l       list links, pick one by number
b       back
r       reload
q       quit
```

## Install

```
git clone https://github.com/YOU/mdnav
cd mdnav
./install.sh
```

Requires [`mdcat`](#installing-mdcat), `python3`, and bash 3.2 or newer. `install.sh` symlinks
`mdnav` into `~/.local/bin` and registers the `mdnav://` scheme with your
desktop. `./uninstall.sh` removes both, including the registry keys on WSL.

### Locked-down machines

Clicking needs the `mdnav://` scheme registered, and on Windows the registry is
the only mechanism for that. The keys go under `HKEY_CURRENT_USER`, so no admin
rights are involved and it usually works on managed laptops — but some are
locked down further.

If the write fails, `install.sh` says so and leaves everything else working. It
also writes `mdnav-install.reg` and `mdnav-uninstall.reg` into
`%LOCALAPPDATA%\mdnav\`, so you can review the change, apply it by
double-clicking, or hand it to whoever administers the machine. It adds nothing
outside `HKEY_CURRENT_USER\Software\Classes\mdnav`.

To skip registration entirely:

```
./install.sh --no-scheme
```

mdnav works without it — you follow links with `l` and a number rather than by
clicking. You don't need to install anything at all for that; `./bin/mdnav` runs
as-is.

### Installing mdcat

```
brew install mdcat          # macOS
pacman -S mdcat             # Arch
cargo install mdcat         # anywhere with a Rust toolchain
```

Prebuilt binaries are on [mdcat's releases
page](https://github.com/swsnr/mdcat/releases). It is not packaged for Debian
or Ubuntu.

Building with `cargo` on Debian/Ubuntu needs the OpenSSL headers first,
otherwise the build fails partway through on `openssl-sys`:

```
sudo apt install pkg-config libssl-dev
```

### Images

mdcat picks an image protocol by asking the terminal, and gets it wrong on
Windows Terminal — it concludes `ansi` and drops images silently, with no
warning that it did. mdnav probes for sixel itself and passes the answer
explicitly, so images work without configuration.

Plain `mdcat` still needs to be told, so `install.sh` offers to add this to
your shell rc:

```
export MDCAT_IMAGE_PROTOCOL=sixel
```

Override the choice for mdnav alone with `MDNAV_IMAGE_PROTOCOL`.

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
