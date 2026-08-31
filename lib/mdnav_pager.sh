# Chunking pre-rendered mdcat output for more(1)-style paging.
#
# Deliberately no screen ownership: nothing is redrawn, and the alternate
# screen is not used. Output accumulates in the terminal's own scrollback,
# so scrolling back is the terminal's job -- which is the only thing that
# renders a partially-visible image correctly, and does it without the
# flicker of repainting a page per keystroke.
#
# The consequence is that rows consumed cannot be measured once the screen
# is full (the cursor stops advancing and the display scrolls instead), so
# an image simply ends the chunk it appears in. Images are tall; pausing
# after one is what you would want anyway.

# Swallow anything the terminal has already sent that we did not ask for --
# mdcat queries the terminal itself when rendering images, and those replies
# arrive on our stdin, where they would otherwise be read as keystrokes.
mdnav_drain_input() {
    local junk
    while IFS= read -rsn1 -t 0.05 junk; do :; done
}

# mdnav_print_chunk <rows-available>
# Prints from BUFFER_INDEX until a screenful is out or an image is printed.
# Advances BUFFER_INDEX.
mdnav_print_chunk() {
    local avail="$1"
    local printed=0 line

    while [ "$BUFFER_INDEX" -lt "${#BUFFER_LINES[@]}" ]; do
        line="${BUFFER_LINES[$BUFFER_INDEX]}"

        case "$line" in
            *$'\eP'*|*$'\e_G'*)
                # An image is usually taller than the screen, so printing it
                # after text scrolls that text away before it can be read.
                # Give it a screenful of its own: stop here and let it lead
                # the next chunk.
                [ "$printed" -gt 0 ] && return 0

                printf '%s\n' "$line"
                BUFFER_INDEX=$(( BUFFER_INDEX + 1 ))
                # Its height is decided by the terminal as it rasterises and
                # cannot be counted from here, so end the chunk.
                return 0 ;;
        esac

        printf '%s\n' "$line"
        BUFFER_INDEX=$(( BUFFER_INDEX + 1 ))
        printed=$(( printed + 1 ))
        [ "$printed" -ge "$avail" ] && return 0
    done
    return 0
}

mdnav_at_end() {
    [ "$BUFFER_INDEX" -ge "${#BUFFER_LINES[@]}" ]
}
