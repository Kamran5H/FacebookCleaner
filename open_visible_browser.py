"""
Launches a dedicated visible browser window for Facebook login with elevated foreground focus
and isolated session profile.
"""
import ctypes
from pathlib import Path
import subprocess
import sys
import time

BASE_DIR = Path(__file__).resolve().parent
SESSION_DIR = BASE_DIR / "fb_session_edge"
SESSION_DIR.mkdir(parents=True, exist_ok=True)

def open_visible():
    edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    edge_path_64 = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    chrome_path_x86 = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

    exe = None
    for p in [edge_path, edge_path_64, chrome_path, chrome_path_x86]:
        if Path(p).exists():
            exe = p
            break

    if not exe:
        import webbrowser
        webbrowser.open("https://www.facebook.com")
        return

    cmd = [
        exe,
        f"--user-data-dir={str(SESSION_DIR)}",
        "--new-window",
        "--start-maximized",
        "--disable-notifications",
        "https://www.facebook.com"
    ]
    print(f"Opening visible window with: {' '.join(cmd)}")
    subprocess.Popen(cmd)
    time.sleep(1.8)

    # Bring to foreground using Win32 API
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        current_thread_id = kernel32.GetCurrentThreadId()
        foreground_hwnd = user32.GetForegroundWindow()
        foreground_thread_id = user32.GetWindowThreadProcessId(foreground_hwnd, None)

        def enum_handler(hwnd, extra):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value
                    if any(k in title for k in ["Facebook", "Edge", "Chrome"]):
                        if foreground_thread_id != current_thread_id:
                            user32.AttachThreadInput(current_thread_id, foreground_thread_id, True)
                        user32.ShowWindow(hwnd, 9)
                        user32.ShowWindow(hwnd, 3)
                        user32.BringWindowToTop(hwnd)
                        user32.SetForegroundWindow(hwnd)
                        if foreground_thread_id != current_thread_id:
                            user32.AttachThreadInput(current_thread_id, foreground_thread_id, False)
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        user32.EnumWindows(WNDENUMPROC(enum_handler), 0)
    except Exception as e:
        print(f"Foreground hook info: {e}")

if __name__ == "__main__":
    open_visible()
