#!/usr/bin/env bash
# What the pager is supposed to do when it is driven.
#
# Every case here failed at some point: a link that went nowhere, an
# anchor that scrolled to the entry pointing at it rather than to the
# heading, a bar whose buttons did nothing. Needs a terminal and an mdcat
# to render with, and says so and stops rather than failing without one.
set -u

here="$(cd "$(dirname "$0")" && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

if ! command -v "${MDCAT_BIN:-mdcat}" >/dev/null 2>&1; then
    echo "  no mdcat: skipping the pager tests"
    exit 0
fi

passed=0
failed=0

drive() {   # rows cols file [keys...]
    python3 "$here/drive.py" "$@" 2>/dev/null
}

# The last thing written to the status bar, which says where we ended up.
last_bar() {
    grep -ao $'\x1b\[0m\x1b\[7m[^\x1b]*' | tail -1 | sed 's/.*\x1b\[7m//'
}

check() {   # description, haystack, needle
    if printf '%s' "$2" | grep -qF "$3"; then
        passed=$(( passed + 1 ))
    else
        failed=$(( failed + 1 ))
        printf '    %s\n      wanted %s\n      in     %s\n' "$1" "$3" "$2"
    fi
}

# --- a document to walk around in -------------------------------------
mkdir -p "$work/notes"
cat > "$work/notes/target.md" <<'EOF'
# Target Doc

## First Section
EOF
for i in $(seq 1 40); do echo "filler $i" >> "$work/notes/target.md"; echo >> "$work/notes/target.md"; done
cat >> "$work/notes/target.md" <<'EOF'
## Late Section

the end
EOF
cat > "$work/doc.md" <<'EOF'
# Doc

## Contents

- [Late Section](notes/target.md#late-section)
- [a whole file](notes/target.md)
- [this document](#contents)

| where | link |
|---|---|
| cell | [in a table](notes/target.md) |
EOF

echo "  following links"
out="$(drive 24 90 "$work/doc.md" '\e[<0;6;8M' '\e[<0;6;8m' '\e[<35;70;20M' | last_bar)"
check "a cross-file anchor opens the file" "$out" "target.md"
# Somewhere other than the top: a section far down a file lands either at
# a percentage or, when the file ends before a screenful, at "end".
if printf '%s' "$out" | grep -q " top "; then
    failed=$(( failed + 1 )); printf '    it scrolled to the section\n      still at the top: %s\n' "$out"
else
    passed=$(( passed + 1 ))
fi

out="$(drive 24 90 "$work/doc.md" '\e[<0;6;9M' '\e[<0;6;9m' '\e[<35;70;20M' | last_bar)"
check "a plain file link opens at the top" "$out" "top"

echo "  going back"
out="$(drive 24 90 "$work/doc.md" '\e[<0;6;9M' '\e[<0;6;9m' 'p' '\e[<35;70;20M' | last_bar)"
check "p returns to the document" "$out" "doc.md"

echo "  the buttons on the bar"
out="$(drive 24 90 "$work/doc.md" '\e[<0;6;9M' '\e[<0;6;9m' '\e[<0;66;24M' '\e[<0;66;24m' '\e[<35;70;20M' | last_bar)"
check "clicking [p back] goes back" "$out" "doc.md"
out="$(drive 24 90 "$work/doc.md" | grep -c '\[q quit\]')"
check "the bar offers the buttons" "$out" "1"

echo "  the link list"
out="$(drive 24 90 "$work/doc.md" 'l' | last_bar)"
check "carries a bar of its own" "$out" "a number to follow"
out="$(drive 24 90 "$work/doc.md" 'l' '2\r' '\e[<35;70;20M' | last_bar)"
check "and a number follows that link" "$out" "target.md"
out="$(drive 24 90 "$work/doc.md" '\e[<0;6;9M' '\e[<0;6;9m' 'l' '\e[<0;76;24M' '\e[<0;76;24m' '\e[<35;70;20M' | last_bar)"
check "its [p back] button answers too" "$out" "doc.md"
out="$(drive 24 90 "$work/doc.md" 'l' '\e[<0;10;2M' '\e[<0;10;2m' '\e[<35;70;20M' | last_bar)"
check "and a line of the list can be clicked" "$out" "target.md"
out="$(drive 24 90 "$work/doc.md" 'l' 'zzz\r' '\e[<35;70;20M' | last_bar)"
check "letters are not collected as a number" "$out" "doc.md"

echo "  a link in a table cell"
out="$(drive 24 90 "$work/doc.md" '\e[<0;12;15M' '\e[<0;12;15m' '\e[<35;70;20M' | last_bar)"
check "is followed like any other" "$out" "target.md"

echo "  a directory"
out="$(drive 24 90 "$work/notes" | last_bar)"
check "opens as a listing" "$out" "notes"

echo
if [ "$failed" -gt 0 ]; then
    echo "  $failed of $(( passed + failed )) failed"
    exit 1
fi
echo "  $passed checks passed"
