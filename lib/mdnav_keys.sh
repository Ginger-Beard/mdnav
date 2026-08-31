# Key decoding for the pager. Sets KEY to a name, or returns 1 on timeout.
#
# Terminals send arrows and page keys as escape sequences, so a bare
# one-character read cannot tell them from a literal Escape. The follow-up
# reads use a short timeout for that reason.
#
# Replies to terminal queries arrive on the same input, and mdcat issues
# such queries while rendering images. Those are recognised and discarded
# rather than mistaken for keys -- a cursor-position reply like \e[66;1R
# starts identically to a PgDn.

mdnav_read_key() {
    KEY=""
    local c c2 ch seq
    # Polled alongside the click FIFO, so this is a latency floor on every
    # keystroke, not just a timeout.
    IFS= read -rsn1 -t "${MDNAV_KEY_POLL:-0.03}" c || return 1

    if [ "$c" != $'\e' ]; then
        case "$c" in
            " ")            KEY="space" ;;
            $'\x7f'|$'\b')  KEY="backspace" ;;
            "")             KEY="enter" ;;
            *)              KEY="char:$c" ;;
        esac
        return 0
    fi

    IFS= read -rsn1 -t 0.05 c2 || { KEY="escape"; return 0; }
    if [ "$c2" != "[" ] && [ "$c2" != "O" ]; then
        KEY="escape"
        return 0
    fi

    # Read to the sequence's final byte instead of guessing from the first,
    # so a query reply can be told apart from a key.
    seq=""
    while IFS= read -rsn1 -t 0.05 ch; do
        seq="$seq$ch"
        case "$ch" in
            [A-Za-z~]) break ;;
        esac
    done

    case "$seq" in
        A)    KEY="up" ;;
        B)    KEY="down" ;;
        C)    KEY="right" ;;
        D)    KEY="left" ;;
        H)    KEY="home" ;;
        F)    KEY="end" ;;
        5~)   KEY="pgup" ;;
        6~)   KEY="pgdn" ;;
        \<*M) KEY="$(mdnav_mouse_key "$seq")" ;;
        \<*m) KEY="ignore" ;;        # button release
        *R|*t|*c) KEY="ignore" ;;    # cursor position, size, device attributes
        *)    KEY="escape" ;;
    esac
    return 0
}

# SGR mouse report: <button;column;rowM. Only the wheel interests us --
# clicks are left to the terminal, which activates hyperlinks itself even
# while mouse reporting is on.
mdnav_mouse_key() {
    local seq="$1" btn
    btn="${seq#<}"
    btn="${btn%%;*}"
    case "$btn" in
        64) printf 'wheel-up' ;;
        65) printf 'wheel-down' ;;
        *)  printf 'ignore' ;;
    esac
}
