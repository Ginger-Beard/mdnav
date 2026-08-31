#!/usr/bin/env bash
# Install mdnav and register the mdnav:// scheme with the desktop.
#
# Linux: an XDG .desktop entry claiming x-scheme-handler/mdnav.
# WSL:   clicks are handled by Windows, not Linux, so the scheme is
#        registered under HKCU and dispatched back through wsl.exe.
#
# --no-scheme installs the commands only. mdnav still works without the
# scheme registered; you navigate with `l` instead of clicking.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bindir="${BINDIR:-$HOME/.local/bin}"
no_scheme=0

for arg in "$@"; do
    case "$arg" in
        --no-scheme) no_scheme=1 ;;
        -h|--help)
            echo "usage: ./install.sh [--no-scheme]"
            echo "  --no-scheme  install commands only; skip registering mdnav://"
            exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

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

if [ "$no_scheme" = 1 ]; then
    echo
    echo "skipped scheme registration (--no-scheme)."
    echo "mdnav works; use 'l' to follow links by number instead of clicking."
    exit 0
fi

if is_wsl; then
    distro="${WSL_DISTRO_NAME:?cannot determine WSL distro name}"
    appdata="$(cmd.exe /c 'echo %LOCALAPPDATA%' 2>/dev/null | tr -d '\r')"
    [ -n "$appdata" ] || { echo "could not read %LOCALAPPDATA%" >&2; exit 1; }
    target_dir="$(wslpath -u "$appdata")/mdnav"
    mkdir -p "$target_dir"

    # Launched with wscript.exe so no console window flashes on each click.
    # --exec avoids a shell on the Linux side, so no quoting games with the URI.
    cat > "$target_dir/mdnav-open.vbs" <<VBS
Option Explicit
Dim sh, uri, cmd
If WScript.Arguments.Count = 0 Then WScript.Quit 1
Set sh = CreateObject("WScript.Shell")
uri = WScript.Arguments(0)
cmd = "wsl.exe -d $distro --exec $here/bin/mdnav-open """ & uri & """"
sh.Run cmd, 0, False
VBS

    vbs_win="$appdata\\mdnav\\mdnav-open.vbs"
    vbs_reg="${vbs_win//\\/\\\\}"

    # Written whether or not the automatic registration works, so the change
    # can be reviewed, applied by hand, or passed to whoever administers the
    # machine.
    cat > "$target_dir/mdnav-install.reg" <<REG
Windows Registry Editor Version 5.00

[HKEY_CURRENT_USER\\Software\\Classes\\mdnav]
@="URL:mdnav Protocol"
"URL Protocol"=""

[HKEY_CURRENT_USER\\Software\\Classes\\mdnav\\shell\\open\\command]
@="wscript.exe \\"$vbs_reg\\" \\"%1\\""
REG
    cat > "$target_dir/mdnav-uninstall.reg" <<REG
Windows Registry Editor Version 5.00

[-HKEY_CURRENT_USER\\Software\\Classes\\mdnav]
REG

    registered=0
    if reg.exe add 'HKCU\Software\Classes\mdnav' /ve /d 'URL:mdnav Protocol' /f >/dev/null 2>&1 &&
       # No /d: the value only needs to exist, and empty args do not marshal
       # reliably through WSL interop.
       reg.exe add 'HKCU\Software\Classes\mdnav' /v 'URL Protocol' /f >/dev/null 2>&1 &&
       reg.exe add 'HKCU\Software\Classes\mdnav\shell\open\command' /ve \
           /d "wscript.exe \"$vbs_win\" \"%1\"" /f >/dev/null 2>&1; then
        registered=1
    fi

    if [ "$registered" = 1 ]; then
        say "registered mdnav:// under HKCU"
        say "handler: $vbs_win"
        echo
        echo "note: Windows Terminal shows a confirmation dialog when you ctrl+click"
        echo "      a non-web scheme, and offers no setting to suppress it."
    else
        echo
        echo "could not write the registry (this is often locked down on managed"
        echo "machines). Everything else is installed, and mdnav works -- use 'l'"
        echo "to follow links by number."
        echo
        echo "To enable clicking, apply this by hand (no admin rights needed --"
        echo "it only writes to your own user hive):"
        echo
        echo "  $appdata\\mdnav\\mdnav-install.reg"
        echo
        echo "Double-click it, or have it reviewed first -- it is three lines and"
        echo "adds nothing outside HKEY_CURRENT_USER\\Software\\Classes\\mdnav."
        echo "To reverse: mdnav-uninstall.reg, in the same folder."
    fi
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
