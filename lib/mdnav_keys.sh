# Key and mouse decoding.
#
# Input is read a chunk at a time rather than a byte at a time. With motion
# reporting on, the terminal sends an event for every pixel the mouse
# moves, and a read per byte cannot keep pace with that -- the display ends
# up behind the input, which reads as the whole thing being slow.
#
# Sets KEY to a name. For mouse events it also sets MOUSE_BTN, MOUSE_COL
# and MOUSE_ROW. Returns 1 when nothing is waiting.

INPUT_BUF=""

# Held in variables: a pattern written inline has its quoting eaten before
# the match ever sees it.
MDNAV_MOUSE_RE=$'^\e\\[<([0-9]+);([0-9]+);([0-9]+)([Mm])'
MDNAV_CSI_RE=$'^\e\\[([0-9;]*)([A-Za-z~])'
MDNAV_SS3_RE=$'^\eO([A-Za-z])' 

mdnav_take() {   # drop <n> characters from the front of the buffer
    INPUT_BUF="${INPUT_BUF:$1}"
}

mdnav_read_key() {
    KEY=""
    local chunk=""
    if [ -z "$INPUT_BUF" ]; then
        # -d '' so a newline does not end the read: Return is a key like any
        # other here, not a delimiter.
        IFS= read -rsn 512 -d '' -t "${MDNAV_KEY_POLL:-0.03}" chunk
        INPUT_BUF="$INPUT_BUF$chunk"
        [ -n "$INPUT_BUF" ] || return 1
    fi

    local c="${INPUT_BUF:0:1}"
    if [ "$c" != $'\e' ]; then
        mdnav_take 1
        case "$c" in
            " ")                  KEY="space" ;;
            $'\x7f'|$'\b')        KEY="backspace" ;;
            $'\n'|$'\r')          KEY="enter" ;;
            *)                    KEY="char:$c" ;;
        esac
        return 0
    fi

    # An escape sequence may be split across chunks; give the rest a moment
    # to arrive before deciding this is a bare Escape.
    if [ "${#INPUT_BUF}" -lt 3 ]; then
        IFS= read -rsn 32 -d '' -t 0.02 chunk
        INPUT_BUF="$INPUT_BUF$chunk"
    fi

    # SGR mouse: <button;column;row followed by M (press or motion) or m.
    if [[ "$INPUT_BUF" =~ $MDNAV_MOUSE_RE ]]; then
        MOUSE_BTN="${BASH_REMATCH[1]}"
        MOUSE_COL="${BASH_REMATCH[2]}"
        MOUSE_ROW="${BASH_REMATCH[3]}"
        local action="${BASH_REMATCH[4]}"
        mdnav_take "${#BASH_REMATCH[0]}"
        case "$MOUSE_BTN" in
            64) KEY="wheel-up" ;;
            65) KEY="wheel-down" ;;
            *)
                # 32 and up with no button held is the mouse simply moving.
                if [ "$action" = "M" ] && [ "$MOUSE_BTN" -ge 32 ]; then
                    KEY="motion"
                else
                    KEY="ignore"
                fi ;;
        esac
        return 0
    fi

    if [[ "$INPUT_BUF" =~ $MDNAV_CSI_RE ]]; then
        local params="${BASH_REMATCH[1]}" final="${BASH_REMATCH[2]}"
        mdnav_take "${#BASH_REMATCH[0]}"
        case "$final$params" in
            A)    KEY="up" ;;
            B)    KEY="down" ;;
            C)    KEY="right" ;;
            D)    KEY="left" ;;
            H)    KEY="home" ;;
            F)    KEY="end" ;;
            "~5") KEY="pgup" ;;
            "~6") KEY="pgdn" ;;
            # Replies to questions we asked the terminal: cursor position,
            # size, device attributes. Not keys.
            R*|t*|c*) KEY="ignore" ;;
            *)    KEY="escape" ;;
        esac
        return 0
    fi

    if [[ "$INPUT_BUF" =~ $MDNAV_SS3_RE ]]; then
        local final="${BASH_REMATCH[1]}"
        mdnav_take "${#BASH_REMATCH[0]}"
        case "$final" in
            A) KEY="up" ;;
            B) KEY="down" ;;
            C) KEY="right" ;;
            D) KEY="left" ;;
            *) KEY="escape" ;;
        esac
        return 0
    fi

    mdnav_take 1
    KEY="escape"
    return 0
}

# Anything already waiting is thrown away -- replies to terminal queries,
# and motion from before whatever just happened.
mdnav_drain_keys() {
    local chunk=""
    INPUT_BUF=""
    while IFS= read -rsn 512 -d '' -t 0.02 chunk; do
        :
    done
}
