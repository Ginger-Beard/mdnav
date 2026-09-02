#!/usr/bin/env python3
"""What to do with a file someone clicked.

Prints one word:

    markdown   render it as a document
    text       show it here, highlighted, with line numbers
    desktop    hand it to whatever opens such things
    refuse     do neither

Nothing here trusts a file's name. What it is, is read from what is in it:
text is recognised by reading it, and a picture or a document by the bytes
every one of them starts with. A program renamed to look like a PDF is
still a program, and is refused.

Handing something over is allowed only for kinds that are certainly
documents or media, and never as a fallback for "not recognised". That way
round matters, and on every system, because opening and running are the
same gesture nearly everywhere:

    Windows   `explorer.exe` starts a .exe, .bat, .cmd, .ps1, .msi, .lnk,
              .scr, .hta and more; the extension alone decides.
    macOS     `open` launches a .app bundle, runs a .command, and starts
              an installer for a .pkg or a .dmg.
    Linux     `xdg-open` follows the desktop's own rules, which for a
              .desktop file or a script with the executable bit set can
              mean running it.

Listing what is safe can only be too small, which costs a click. Listing
what is unsafe can be out of date, which runs a program -- and it would
have to be right about three systems at once.

usage: mdnav_kind.py <path>
"""

import os
import sys

MARKDOWN = {".md", ".markdown", ".mkd", ".mdown", ".mkdn", ".mdwn"}

# What a file says it is in its first bytes. Only things that are looked
# at rather than run: no archive, no installer, no program.
MAGIC = [
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"BM", "bmp"),
    (b"II*\x00", "tiff"),
    (b"MM\x00*", "tiff"),
    (b"\x00\x00\x01\x00", "ico"),
    (b"%PDF-", "pdf"),
    (b"OggS", "ogg"),
    (b"ID3", "mp3"),
    (b"\xff\xfb", "mp3"),
    (b"\x1a\x45\xdf\xa3", "matroska"),
    (b"fLaC", "flac"),
]

# Inside a zip, what marks it as a document rather than a program. A .jar
# and a .docx are both zips; only one of them is safe to hand over.
ZIP_DOCUMENTS = ("[Content_Types].xml", "mimetype", "word/", "xl/", "ppt/")

SNIFF = 8192


def magic_kind(head, path):
    """What the bytes say this is, or None."""
    for signature, name in MAGIC:
        if head.startswith(signature):
            return name
    # RIFF containers name themselves four bytes in.
    if head[:4] == b"RIFF" and head[8:12] in (b"WEBP", b"WAVE", b"AVI "):
        return head[8:12].decode("ascii").strip().lower()
    # ISO base media -- mp4, m4a, mov -- says so at offset four.
    if head[4:8] == b"ftyp":
        return "mp4"
    if head[:4] == b"PK\x03\x04":
        return zip_kind(path)
    return None


def zip_kind(path):
    """Whether a zip is an office document, rather than something else."""
    try:
        import zipfile
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()[:32]
    except Exception:
        return None
    for name in names:
        if name.startswith(ZIP_DOCUMENTS):
            return "document"
    return None


def looks_like_text(head):
    """Whether the first few kilobytes read as text.

    The file is asked rather than its name, so a Makefile, a Dockerfile and
    a LICENSE are all readable, and something calling itself .txt while
    being a binary is not mistaken for one.
    """
    if not head:
        return True
    if b"\x00" in head:
        return False
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        # Not UTF-8, but a single-byte encoding is still text if it is
        # mostly printable. Control characters are what binary looks like.
        control = sum(1 for byte in head
                      if byte < 32 and byte not in (9, 10, 13))
        return control / len(head) < 0.02
    return True


# A macOS bundle is a directory that is a program. There are no bytes to
# read for a directory, so the name is the only thing to go on -- and here
# it is enough, because these names are what makes them bundles.
BUNDLES = (".app", ".bundle", ".framework", ".plugin", ".kext", ".xpc")


def kind(path):
    if os.path.isdir(path):
        if path.rstrip("/").lower().endswith(BUNDLES):
            return "refuse"
        return "markdown"
    if not os.path.isfile(path):
        return "refuse"
    if os.path.splitext(path)[1].lower() in MARKDOWN:
        return "markdown"
    try:
        with open(path, "rb") as handle:
            head = handle.read(SNIFF)
    except OSError:
        return "refuse"
    # Asked before the file is read as text, because a picture may well be
    # text -- an SVG is XML -- and is still a picture.
    if magic_kind(head, path):
        return "desktop"
    if head.lstrip()[:4] == b"<svg" or b"<svg" in head[:512]:
        return "desktop"
    if looks_like_text(head):
        return "text"
    return "refuse"


def main():
    sys.stdout.write(kind(sys.argv[1]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.stdout.write("refuse")
        sys.exit(0)
