# Key decoding for the pager. Sets KEY to a name, or returns 1 on timeout.
#
# Terminals send arrows and page keys as escape sequences, so a bare
# one-character read cannot tell them from a literal Escape. The follow-up
# reads use a short timeout for that reason.

mdnav_read_key() {
    KEY=""
    local c c2 c3 junk
    IFS= read -rsn1 -t 0.15 c || return 1

    if [ "$c" = $'\e' ]; then
        IFS= read -rsn1 -t 0.05 c2 || { KEY="escape"; return 0; }
        if [ "$c2" != "[" ] && [ "$c2" != "O" ]; then
            KEY="escape"; return 0
        fi
        IFS= read -rsn1 -t 0.05 c3 || { KEY="escape"; return 0; }
        case "$c3" in
            A) KEY="up" ;;
            B) KEY="down" ;;
            C) KEY="right" ;;
            D) KEY="left" ;;
            H) KEY="home" ;;
            F) KEY="end" ;;
            5) IFS= read -rsn1 -t 0.05 junk; KEY="pgup" ;;
            6) IFS= read -rsn1 -t 0.05 junk; KEY="pgdn" ;;
            *) KEY="escape" ;;
        esac
        return 0
    fi

    case "$c" in
        " ")      KEY="space" ;;
        $'\x7f'|$'\b') KEY="backspace" ;;
        "")       KEY="enter" ;;
        *)        KEY="char:$c" ;;
    esac
    return 0
}
