"""
Creates / refreshes the desktop shortcut for Facebook Zenith Cleaner.

Run this after regenerating the icon (`python create_icon.py`) so Windows picks
up the new artwork -- the shell caches icons per .lnk, so the shortcut has to be
rewritten and the icon cache nudged for the change to show up on the desktop.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TARGET_VBS = BASE_DIR / "launch.vbs"
ICON_PATH = BASE_DIR / "fb_cleaner.ico"
SHORTCUT_NAME = "Facebook Zenith Cleaner.lnk"


def desktop_dirs() -> list[Path]:
    """OneDrive-redirected desktops and the plain one; write to whichever exist."""
    profile = Path(os.environ.get("USERPROFILE", str(Path.home())))
    found = []
    onedrive = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer")
    if onedrive:
        found.append(Path(onedrive) / "Desktop")
    found.append(profile / "OneDrive" / "Desktop")
    found.append(profile / "Desktop")

    unique, seen = [], set()
    for d in found:
        key = str(d).lower()
        if key not in seen and d.is_dir():
            seen.add(key)
            unique.append(d)
    return unique


def write_shortcut(path: Path) -> bool:
    try:
        import win32com.client
    except ImportError:
        return write_shortcut_powershell(path)

    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        sc = shell.CreateShortCut(str(path))
        sc.Targetpath = "wscript.exe"
        sc.Arguments = f'"{TARGET_VBS}"'
        sc.WorkingDirectory = str(BASE_DIR)
        sc.IconLocation = f"{ICON_PATH},0"
        sc.Description = "Facebook Zenith Cleaner - triage and remove friends, groups and pages"
        sc.WindowStyle = 7  # start minimized; the dashboard opens as its own window
        sc.save()
        return True
    except Exception as e:
        print(f"[WARN] win32com failed ({e}); trying PowerShell...")
        return write_shortcut_powershell(path)


def write_shortcut_powershell(path: Path) -> bool:
    ps = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{path}'); "
        "$s.TargetPath = 'wscript.exe'; "
        f"$s.Arguments = '\"{TARGET_VBS}\"'; "
        f"$s.WorkingDirectory = '{BASE_DIR}'; "
        f"$s.IconLocation = '{ICON_PATH},0'; "
        "$s.Description = 'Facebook Zenith Cleaner'; "
        "$s.WindowStyle = 7; "
        "$s.Save()"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"[ERROR] PowerShell fallback failed: {result.stderr.strip()}")
        return False
    return True


def refresh_icon_cache():
    """Windows caches .lnk icons; without this the desktop keeps the old artwork."""
    try:
        import ctypes
        SHCNE_ASSOCCHANGED = 0x08000000
        SHCNF_IDLIST = 0x0000
        ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
    except Exception:
        pass


def main() -> int:
    if not ICON_PATH.exists():
        print("[INFO] Icon missing -- generating it first.")
        subprocess.run([sys.executable, str(BASE_DIR / "create_icon.py")], check=False)
    if not TARGET_VBS.exists():
        print(f"[ERROR] Missing launcher: {TARGET_VBS}")
        return 1

    targets = desktop_dirs()
    if not targets:
        print("[ERROR] No Desktop folder found.")
        return 1

    ok = 0
    for d in targets:
        path = d / SHORTCUT_NAME
        # Rewriting in place is what makes Explorer re-read the icon.
        if path.exists():
            try:
                path.unlink()
            except Exception as e:
                print(f"[WARN] Could not replace {path}: {e}")
        if write_shortcut(path):
            print(f"[OK] Shortcut written: {path}")
            ok += 1

    refresh_icon_cache()
    if ok:
        print("[OK] Desktop icon updated. Press F5 on the desktop if it still looks stale.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
