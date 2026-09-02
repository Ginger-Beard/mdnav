# Tests

Two tiers, because they need different things.

`test_helpers.py` covers the Python that does the thinking -- resolving a
link, naming an anchor, measuring a line, finding a table. It needs
nothing but Python, so it runs anywhere in a second, and it is where most
of the behaviour lives.

`test_pager.sh` drives the pager itself through a pseudo-terminal. It
needs a terminal and an `mdcat` to render with, so it is slower and is
skipped where those are missing rather than failing.

    python3 tests/test_helpers.py        # fast, no dependencies
    bash tests/test_pager.sh             # needs mdcat
