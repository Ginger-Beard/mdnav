# Paging over pre-rendered mdcat output.
#
# The hard part is that a sixel image is a single line in the buffer but
# occupies many rows on screen, and how many is decided by the terminal
# while it rasterises -- it is not derivable from the bytes. So: count text
# lines, and after any line carrying image data, ask the terminal where the
# cursor actually ended up (CSI 6n).

# Sets CURSOR_ROW to the cursor's current row, 1-based.
#
# Deliberately not `CURSOR_ROW=$(...)`: inside a command substitution the
# query would be written to the capture pipe rather than the terminal, and
# no reply would ever come back.
mdnav_cursor_row() {
    local reply r
    CURSOR_ROW=0
    printf '\e[6n' > /dev/tty 2>/dev/null || return 1
    IFS= read -r -d R -t 0.4 reply < /dev/tty 2>/dev/null || return 1
    r="${reply#*\[}"
    r="${r%%;*}"
    case "$r" in
        ''|*[!0-9]*) return 1 ;;
        *) CURSOR_ROW="$r"; return 0 ;;
    esac
}

# Swallow anything the terminal has already sent that we did not ask for --
# mdcat queries the terminal itself when rendering images, and those replies
# arrive on our stdin, where they would otherwise be read as keystrokes.
mdnav_drain_input() {
    local junk
    while IFS= read -rsn1 -t 0.05 junk; do :; done
}

# mdnav_draw_page <start-index> <rows-available>
# Writes lines from BUFFER_LINES starting at <start-index> until the screen
# is full. Sets PAGE_NEXT to the first index not shown.
mdnav_draw_page() {
    local start="$1" avail="$2"
    local row=1 i="$start" line

    printf '\e[H\e[2J'
    while [ "$i" -lt "${#BUFFER_LINES[@]}" ]; do
        line="${BUFFER_LINES[$i]}"
        printf '%s\n' "$line"
        case "$line" in
            *$'\eP'*|*$'\e_G'*)
                # Only the terminal knows how tall that turned out.
                if mdnav_cursor_row; then
                    row="$CURSOR_ROW"
                else
                    row=$(( row + 1 ))
                fi ;;
            *) row=$(( row + 1 )) ;;
        esac
        i=$(( i + 1 ))
        [ "$row" -gt "$avail" ] && break
    done
    PAGE_NEXT="$i"
}
