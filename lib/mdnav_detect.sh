# Shared image-protocol detection. Sourced by bin/mdnav and install.sh.
#
# mdcat's own auto-detection reports "ansi" for Windows Terminal even when
# sixel works there, and silently drops images as a result -- which is the
# whole reason this file exists.

# Ask the terminal directly: Primary Device Attributes (CSI c). Sixel-capable
# terminals include 4 among the parameters of the reply.
mdnav_terminal_has_sixel() {
    [ -t 0 ] && [ -t 1 ] || return 1
    local saved reply
    saved="$(stty -g 2>/dev/null)" || return 1
    stty -echo -icanon min 0 time 2 2>/dev/null
    printf '\e[c' > /dev/tty 2>/dev/null
    IFS= read -r -d c -t 0.4 reply < /dev/tty 2>/dev/null
    stty "$saved" 2>/dev/null
    case ";${reply};" in
        *';4;'*) return 0 ;;
    esac
    return 1
}

# Echoes a protocol name for --image-protocol, or nothing to let mdcat choose.
mdnav_image_protocol() {
    if [ -n "${MDNAV_IMAGE_PROTOCOL:-}" ]; then
        printf '%s' "$MDNAV_IMAGE_PROTOCOL"; return
    fi
    if [ -n "${MDCAT_IMAGE_PROTOCOL:-}" ]; then
        printf '%s' "$MDCAT_IMAGE_PROTOCOL"; return
    fi
    if [ -n "${KITTY_WINDOW_ID:-}" ] || case "${TERM:-}" in *kitty*) true ;; *) false ;; esac; then
        printf 'kitty'; return
    fi
    # Ghostty draws images with kitty's protocol and answers no to sixel, so
    # without this it falls past every branch here and shows none. Named
    # rather than asked, because the question below is only about sixel.
    if [ "${TERM_PROGRAM:-}" = "ghostty" ] || case "${TERM:-}" in *ghostty*) true ;; *) false ;; esac; then
        printf 'kitty'; return
    fi
    if [ "${TERM_PROGRAM:-}" = "iTerm.app" ] || [ "${TERM_PROGRAM:-}" = "WezTerm" ]; then
        printf 'iterm2'; return
    fi
    if mdnav_terminal_has_sixel; then
        printf 'sixel'; return
    fi
    printf ''
}
