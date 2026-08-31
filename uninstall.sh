#!/usr/bin/env bash
# Remove everything install.sh created: the symlinks, and the scheme
# registration (HKCU on WSL, the .desktop entry on Linux).
set -euo pipefail

bindir="${BINDIR:-$HOME/.local/bin}"
is_wsl() { [ -n "${WSL_DISTRO_NAME:-}" ] || grep -qi microsoft /proc/version 2>/dev/null; }
say() { printf '  %s\n' "$*"; }

echo "removing mdnav"

rm -f "$bindir/mdnav" "$bindir/mdnav-open"
say "removed symlinks from $bindir"

rm -f "${XDG_RUNTIME_DIR:-/tmp}/mdnav-$(id -u).fifo"

if is_wsl; then
    if reg.exe query 'HKCU\Software\Classes\mdnav' >/dev/null 2>&1; then
        reg.exe delete 'HKCU\Software\Classes\mdnav' /f >/dev/null
        say "removed HKCU\\Software\\Classes\\mdnav"
    fi
    appdata="$(cmd.exe /c 'echo %LOCALAPPDATA%' 2>/dev/null | tr -d '\r')"
    if [ -n "$appdata" ]; then
        target="$(wslpath -u "$appdata")/mdnav"
        [ -d "$target" ] && rm -rf "$target" && say "removed $target"
    fi
else
    appdir="$HOME/.local/share/applications"
    if [ -f "$appdir/mdnav.desktop" ]; then
        rm -f "$appdir/mdnav.desktop"
        command -v update-desktop-database >/dev/null 2>&1 && \
            update-desktop-database "$appdir" 2>/dev/null || true
        say "removed $appdir/mdnav.desktop"
    fi
fi

echo "done."
