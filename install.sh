#!/usr/bin/env bash
# Install mdnav and register the mdnav:// scheme with the desktop.
#
# Linux: an XDG .desktop entry claiming x-scheme-handler/mdnav.
# WSL:   clicks are handled by Windows, not Linux, so the scheme is
#        registered under HKCU and dispatched back through wsl.exe.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bindir="${BINDIR:-$HOME/.local/bin}"

is_wsl() { [ -n "${WSL_DISTRO_NAME:-}" ] || grep -qi microsoft /proc/version 2>/dev/null; }

say() { printf '  %s\n' "$*"; }

echo "installing mdnav"

command -v python3 >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 1; }
if ! command -v "${MDCAT_BIN:-mdcat}" >/dev/null 2>&1; then
    echo "warning: mdcat not found on PATH -- install it, or set MDCAT_BIN" >&2
fi

mkdir -p "$bindir"
ln -sf "$here/bin/mdnav" "$bindir/mdnav"
ln -sf "$here/bin/mdnav-open" "$bindir/mdnav-open"
say "linked mdnav, mdnav-open -> $bindir"

case ":$PATH:" in
    *":$bindir:"*) ;;
    *) say "note: $bindir is not on your PATH" ;;
esac

if is_wsl; then
    distro="${WSL_DISTRO_NAME:?cannot determine WSL distro name}"
    appdata="$(cmd.exe /c 'echo %LOCALAPPDATA%' 2>/dev/null | tr -d '\r')"
    [ -n "$appdata" ] || { echo "could not read %LOCALAPPDATA%" >&2; exit 1; }
    windir_wsl="$(wslpath -u "$appdata")/mdnav"
    mkdir -p "$windir_wsl"

    # Launched with wscript.exe so no console window flashes on each click.
    # --exec avoids a shell on the Linux side, so no quoting games with the URI.
    cat > "$windir_wsl/mdnav-open.vbs" <<VBS
Option Explicit
Dim sh, uri, cmd
If WScript.Arguments.Count = 0 Then WScript.Quit 1
Set sh = CreateObject("WScript.Shell")
uri = WScript.Arguments(0)
cmd = "wsl.exe -d $distro --exec $here/bin/mdnav-open """ & uri & """"
sh.Run cmd, 0, False
VBS

    local_win="$appdata\\mdnav\\mdnav-open.vbs"
    reg.exe add 'HKCU\Software\Classes\mdnav' /ve /d 'URL:mdnav Protocol' /f >/dev/null
    # No /d: the value only needs to exist, and empty args do not survive
    # WSL's argument marshaling reliably.
    reg.exe add 'HKCU\Software\Classes\mdnav' /v 'URL Protocol' /f >/dev/null
    reg.exe add 'HKCU\Software\Classes\mdnav\shell\open\command' /ve \
        /d "wscript.exe \"$local_win\" \"%1\"" /f >/dev/null
    say "registered mdnav:// under HKCU"
    say "handler: $local_win"
    echo
    echo "note: Windows Terminal shows a confirmation dialog the first time (and"
    echo "      generally each time) you ctrl+click a non-web scheme. That prompt"
    echo "      is Windows Terminal's, and there is no setting to suppress it."
else
    appdir="$HOME/.local/share/applications"
    mkdir -p "$appdir"
    cat > "$appdir/mdnav.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=mdnav
Comment=Open Markdown links in a running mdnav
Exec="$here/bin/mdnav-open" %u
Terminal=false
NoDisplay=true
MimeType=x-scheme-handler/mdnav;
DESKTOP
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$appdir" 2>/dev/null || true
    fi
    if command -v xdg-mime >/dev/null 2>&1; then
        xdg-mime default mdnav.desktop x-scheme-handler/mdnav
    fi
    say "registered x-scheme-handler/mdnav -> $appdir/mdnav.desktop"
fi

echo
echo "done. try:  mdnav README.md"
