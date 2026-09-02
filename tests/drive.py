#!/usr/bin/env python3
"""Run mdnav in a pseudo-terminal and send it keys and clicks.

The pager cannot be tested by piping at it: it takes over the screen, and
what it does depends on how big the screen is and where the mouse went.
So it gets a terminal of a known size, and its output comes back as the
bytes it wrote.

Keys are given as arguments. "\\r" is a return, "\\e" an escape, so a click
is written as an SGR mouse report: \\e[<0;COL;ROWM to press, m to release.

usage: drive.py <rows> <cols> <file> [key...]
"""

import fcntl
import os
import pty
import select
import struct
import sys
import termios
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    rows, cols, src = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    keys = sys.argv[4:]

    pid, fd = pty.fork()
    if pid == 0:
        os.environ["TERM"] = "xterm-256color"
        os.environ.setdefault("MDNAV_IMAGE_PROTOCOL", "none")
        os.chdir(ROOT)
        os.execvp("bash", ["bash", os.path.join(ROOT, "bin", "mdnav"), src])
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    out = bytearray()

    def pump(seconds):
        end = time.time() + seconds
        while time.time() < end:
            ready, _, _ = select.select([fd], [], [], 0.05)
            if ready:
                try:
                    block = os.read(fd, 65536)
                except OSError:
                    return
                if not block:
                    return
                out.extend(block)

    pump(2.5)
    for key in keys:
        os.write(fd, key.encode().replace(b"\\r", b"\r").replace(b"\\e", b"\x1b"))
        pump(2.0)
    os.write(fd, b"q")
    pump(0.5)
    try:
        os.kill(pid, 9)
        os.waitpid(pid, 0)
    except OSError:
        pass
    sys.stdout.buffer.write(bytes(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
