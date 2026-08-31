# Paging over pre-rendered mdcat output.
#
# The hard part is that a sixel image is a single line in the buffer but
# occupies many rows on screen, and how many is decided by the terminal
# while it rasterises -- it is not derivable from the bytes. So: count text
# lines, and after any line carrying image data, ask the terminal where the
# cursor actually ended up (CSI 6n).

# Row the cursor is on right now, 1-based.
mdnav_cursor_row() {
    local reply r
    printf '\e[6n'
    IFS= read -r -d R -t 0.4 reply 2>/dev/null || { printf '%s' "${LINES_TOTAL:-1}"; return; }
    r="${reply#*\[}"
    r="${r%%;*}"
    case "$r" in
        ''|*[!0-9]*) printf '1' ;;
        *) printf '%s' "$r" ;;
    esac
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
            *$'\eP'*|*$'\e_G'*) row="$(mdnav_cursor_row)" ;;
            *) row=$(( row + 1 )) ;;
        esac
        i=$(( i + 1 ))
        [ "$row" -gt "$avail" ] && break
    done
    PAGE_NEXT="$i"
}
