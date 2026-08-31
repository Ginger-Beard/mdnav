#!/usr/bin/env bash
# Remove everything install.sh created: the symlinks, and the scheme
# registration (HKCU on WSL, the .desktop entry on Linux).
set -euo pipefail

bindir="${BINDIR:-$HOME/.local/bin}"
is_wsl() { [ -n "${WSL_DISTRO_NAME:-}" ] || grep -qi microsoft /proc/version 2>/dev/null; }
is_mac() { [ "$(uname -s)" = "Darwin" ]; }
say() { printf '  %s\n' "$*"; }

echo "removing mdnav"

rm -f "$bindir/mdnav" "$bindir/mdnav-open"
say "removed symlinks from $bindir"

rm -f /tmp/mdnav-"$(id -u)"-*.fifo
rm -rf "${XDG_CACHE_HOME:-$HOME/.cache}/mdnav"

if is_wsl; then
    left_behind=0
    if reg.exe query 'HKCU\Software\Classes\mdnav' >/dev/null 2>&1; then
        if reg.exe delete 'HKCU\Software\Classes\mdnav' /f >/dev/null 2>&1; then
            say "removed HKCU\\Software\\Classes\\mdnav"
        else
            left_behind=1
        fi
    fi
    appdata="$(cmd.exe /c 'echo %LOCALAPPDATA%' 2>/dev/null | tr -d '\r')"
    if [ -n "$appdata" ]; then
        target="$(wslpath -u "$appdata")/mdnav"
        if [ "$left_behind" = 1 ]; then
            # Keep the folder: the .reg file in it is how they undo this.
            echo
            echo "could not remove the registry key. To do it by hand, run:"
            echo "  $appdata\\mdnav\\mdnav-uninstall.reg"
            echo "(leaving $appdata\\mdnav in place, since that file lives there)"
        elif [ -d "$target" ]; then
            rm -rf "$target"
            say "removed $target"
        fi
    fi
elif is_mac; then
    app="$HOME/Applications/mdnav-open.app"
    if [ -d "$app" ]; then
        lsregister=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
        [ -x "$lsregister" ] && "$lsregister" -u "$app" 2>/dev/null || true
        rm -rf "$app"
        say "removed $app"
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
