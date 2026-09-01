"""
Facebook Zenith Cleaner - Core Automation Engine (v2.0)

Architecture
------------
ONE persistent, visible Chromium window, owned by ONE dedicated worker thread.

Playwright's sync API is not thread-safe and a Chromium user-data-dir can only be
held by a single process. The previous design launched a fresh persistent context
per operation and shuffled between three different profile directories on failure,
which meant: the browser you logged into was never the browser that scanned, and
concurrent operations deadlocked on the profile SingletonLock.

Everything now runs as a job on `session`, a single-threaded browser worker:

    session.submit(lambda page, ctx: ...)   # blocking, returns the job's result
    session.submit_async(fn)                # fire-and-forget, returns a Job

Login state is determined by the real `c_user` cookie (not by guessing from file
sizes), and the account owner is identified by that cookie id + the resolved
profile URL, so the owner is protected without blacklisting common names.
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import queue
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

BASE_DIR = Path(__file__).resolve().parent.parent

# One profile, in LOCALAPPDATA (never inside OneDrive -- sync locks corrupt Chromium profiles).
LOCAL_APP_DIR = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
PROFILE_DIR = LOCAL_APP_DIR / "FBCleaner" / "Profile"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

DATA_CACHE_FILE = BASE_DIR / "scanned_data.json"
PURGE_LOG_FILE = BASE_DIR / "purge_history.json"
PURGE_QUEUE_FILE = BASE_DIR / "purge_queue.json"   # crash/power-safe removal checkpoint
LOG_FILE = BASE_DIR / "fb_cleaner.log"

logger = logging.getLogger("fbcleaner")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    _fmt = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    _fh = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
    _fh.setFormatter(_fmt)
    logger.addHandler(_fh)
    # Under pythonw.exe there is no console: sys.stderr is None and a
    # StreamHandler would raise on every log call, killing the launcher silently.
    if sys.stderr is not None:
        _ch = logging.StreamHandler()
        _ch.setFormatter(_fmt)
        logger.addHandler(_ch)
    logger.propagate = False

# Playwright is chatty on the root logger; keep its transport noise out of our file.
logging.getLogger("playwright").setLevel(logging.WARNING)


# ============================================================================
# TEXT NORMALIZATION
# ============================================================================

def normalize_text(text: str) -> str:
    """NFD-normalizes and strips diacritics so stylized Unicode names compare equal."""
    if not text:
        return ""
    nfd = unicodedata.normalize("NFD", str(text))
    stripped = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return " ".join(stripped.lower().split())


# UI chrome that leaks into scraped lists. Matched by EXACT normalized equality only --
# prefix matching used to delete real people ("Home" would eat "Homer Khan").
EXCLUDED_HEADINGS: Set[str] = {
    "home", "friends", "watch", "marketplace", "groups", "gaming", "menu", "facebook",
    "custom lists", "birthdays", "friend requests", "suggestions", "all friends",
    "photos", "videos", "about", "terms", "privacy policy", "privacy center", "reels",
    "posts", "more", "manage", "search", "edit profile", "add to story", "see all",
    "dashboard", "professional dashboard", "following", "followers", "events", "saved",
    "memories", "feeds", "ad manager", "ads manager", "meta business suite", "fundraisers",
    "orders and payments", "recent ad activity", "play games", "gaming video",
    "live videos", "messenger", "notifications", "settings & privacy", "settings",
    "help & support", "display & accessibility", "give feedback", "log out",
    "search friends", "your groups", "your friends", "discover", "create new group",
    "create group", "notifications settings", "see more", "see less", "liked pages",
    "your pages", "pages", "recent", "suggested for you", "people you may know",
    "tv programmes", "tv programs", "books", "music", "movies", "films", "sports",
    "apps and games", "games", "likes", "check-ins", "find friends", "profile",
    "ہوم", "دوست", "گروپس", "گیمنگ", "مینیو", "تمام دوست", "تصاویر", "ویڈیوز",
    "کے بارے میں", "یادیں", "فیڈز", "ایڈز مینیجر", "سیٹنگز", "پیغامات", "نوٹیفکیشن",
    "کتابیں", "موسیقی", "فلمیں", "کھیل", "پسندیدگیاں", "مزید", "سب دیکھیں",
}

# If a scraped card contains any of these, the person is not an active friend.
NON_FRIEND_MARKERS = [
    "add friend", "friend request sent", "request sent", "cancel request",
    "people you may know", "suggested for you", "respond to friend request",
    "confirm", "delete request",
    "دوست شامل کریں", "درخواست بھیجی گئی", "درخواست منسوخ کریں", "آپ شاید جانتے ہیں",
]

# Multi-lingual button/menu labels used by the removal flows.
T = {
    "friends_btn": ["Friends", "Edit friendship", "دوست", "دوستی میں ترمیم"],
    "add_friend": ["Add friend", "Add Friend", "دوست شامل کریں"],
    "unfriend": ["Unfriend", "Remove friend", "دوستی ختم کریں", "دوستی ختم"],
    "confirm": ["Confirm", "Remove", "OK", "تصدیق کریں", "تصدیق", "ہٹائیں"],
    "joined": ["Joined", "شامل ہیں", "شامل ہو چکے ہیں"],
    "join": ["Join group", "Join Group", "Join", "گروپ میں شامل ہوں", "شامل ہوں"],
    "leave_group": ["Leave group", "Leave Group", "گروپ چھوڑیں", "چھوڑیں"],
    "following": ["Following", "فالو کر رہے ہیں"],
    "follow": ["Follow", "فالو کریں"],
    "unfollow": ["Unfollow", "ان فالو کریں"],
    "liked": ["Liked", "پسند کیا"],
    "like": ["Like", "پسند کریں"],
    "unlike": ["Unlike", "ان لائک کریں", "ناپسند کریں"],
    "more": ["More", "See options", "Options", "مزید", "اختیارات"],
}


# ============================================================================
# WINDOWS FOREGROUND HELPER
# ============================================================================

_LAST_FOCUS_TS = 0.0

def focus_browser_window(hwnd_title_hint: str = "Facebook", min_interval: float = 4.0):
    """
    Raises the automation window on Windows. Rate-limited so it cannot fight the
    user for focus while they are typing a password or a 2FA code.
    """
    global _LAST_FOCUS_TS
    if sys.platform != "win32":
        return
    now = time.time()
    if now - _LAST_FOCUS_TS < min_interval:
        return
    _LAST_FOCUS_TS = now

    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # HWND is pointer-sized: c_int truncates on 64-bit and silently breaks EnumWindows.
        LPARAM = ctypes.c_ssize_t
        HWND = ctypes.c_void_p
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, HWND, LPARAM)

        current_thread_id = kernel32.GetCurrentThreadId()
        fg_hwnd = user32.GetForegroundWindow()
        fg_thread_id = user32.GetWindowThreadProcessId(fg_hwnd, None)
        hint = hwnd_title_hint.lower()
        found = []

        def enum_handler(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            if hint in buff.value.lower():
                found.append(hwnd)
                return False
            return True

        user32.EnumWindows(WNDENUMPROC(enum_handler), 0)
        if not found:
            return

        hwnd = found[0]
        attached = False
        if fg_thread_id and fg_thread_id != current_thread_id:
            attached = bool(user32.AttachThreadInput(current_thread_id, fg_thread_id, True))
        user32.ShowWindow(hwnd, 9)          # SW_RESTORE
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        if attached:
            user32.AttachThreadInput(current_thread_id, fg_thread_id, False)
    except Exception as e:  # focus is best-effort, never fatal
        logger.debug(f"focus_browser_window: {e}")


# ============================================================================
# SINGLE-THREADED BROWSER SESSION
# ============================================================================

class Job:
    __slots__ = ("fn", "name", "event", "result", "error")

    def __init__(self, fn: Callable, name: str):
        self.fn = fn
        self.name = name
        self.event = threading.Event()
        self.result: Any = None
        self.error: Optional[BaseException] = None

    def wait(self, timeout: Optional[float] = None):
        if not self.event.wait(timeout):
            raise TimeoutError(f"Browser job '{self.name}' timed out after {timeout}s")
        if self.error:
            raise self.error
        return self.result


class SessionError(RuntimeError):
    """The browser context/window is gone; the caller must relaunch to continue."""
    pass


class TransientError(RuntimeError):
    """
    A recoverable interruption mid-operation -- a navigation timeout, a dropped
    connection, a page that never settled. The purge loop treats these as "pause
    and retry the same item" rather than "this removal failed", so a Wi-Fi blip
    or a power flicker never burns an item or corrupts the count.
    """
    pass


class BlockedError(RuntimeError):
    """
    Facebook served a checkpoint / "temporarily blocked" / captcha wall. Hammering
    the queue against it would fail every item and deepen the block, so the purge
    stops immediately, parks the rest as resumable, and asks the user to clear the
    check in the browser before resuming.
    """
    pass


class BrowserSession:
    """Owns the one and only Playwright context. All page work runs on its thread."""

    def __init__(self, profile_dir: Path = PROFILE_DIR):
        self.profile_dir = profile_dir
        self._jobs: "queue.Queue[Optional[Job]]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._stopped = threading.Event()
        self._start_error: Optional[str] = None
        self._start_lock = threading.Lock()
        self._shutdown = False
        self.browser_kind = "chromium"
        self.last_error: Optional[str] = None

    # -- lifecycle ---------------------------------------------------------

    @property
    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and self._ready.is_set())

    def _migrate_legacy_profile(self):
        """
        v1 shuffled between three profile directories, so an existing Facebook
        login may live in any of them. Copy the newest one across once, so
        upgrading does not force the user to sign in again. Chromium's cookie
        key lives in 'Local State' next to 'Default', so both must come over.
        """
        if (self.profile_dir / "Default" / "Network" / "Cookies").exists():
            return
        legacy_roots = [
            LOCAL_APP_DIR / "FBCleanerChromium",
            LOCAL_APP_DIR / "FBCleanerSession",
            LOCAL_APP_DIR / "FBCleanerChrome",
            LOCAL_APP_DIR / "FBCleanerEdge",
        ]
        candidates = []
        for root in legacy_roots:
            cookies = root / "Default" / "Network" / "Cookies"
            if cookies.exists() and cookies.stat().st_size > 1024:
                candidates.append((cookies.stat().st_mtime, root))
        if not candidates:
            return

        _, src = max(candidates)
        try:
            shutil.copytree(src / "Default", self.profile_dir / "Default", dirs_exist_ok=True)
            for name in ("Local State", "First Run"):
                if (src / name).exists():
                    shutil.copy2(src / name, self.profile_dir / name)
            logger.info(f"Migrated the existing Facebook session from {src.name}.")
        except Exception as e:
            logger.warning(f"Could not migrate the legacy profile from {src}: {e}")

    def _clear_stale_locks(self):
        """A hard-killed Chromium leaves SingletonLock behind and blocks every relaunch."""
        for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            p = self.profile_dir / name
            try:
                if p.is_symlink() or p.exists():
                    p.unlink()
            except Exception:
                pass

    def _kill_profile_owners(self) -> int:
        """
        Kills any leftover browser still holding our user-data-dir. Without this,
        a crashed or orphaned run makes every relaunch fail with
        'Target page, context or browser has been closed' forever.

        The match is on our own private profile path, so this can never touch the
        user's normal Chrome or Edge windows.
        """
        if sys.platform != "win32":
            return 0
        marker = str(self.profile_dir)
        try:
            out = subprocess.run(
                ["wmic", "process", "where",
                 "name='chrome.exe' or name='msedge.exe'",
                 "get", "ProcessId,CommandLine", "/format:csv"],
                capture_output=True, text=True, timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout
        except Exception:
            out = ""

        pids = []
        if marker.lower() in out.lower():
            for line in out.splitlines():
                if marker.lower() in line.lower():
                    pid = line.rstrip().rsplit(",", 1)[-1].strip()
                    if pid.isdigit():
                        pids.append(pid)

        if not pids:
            # wmic is deprecated on Windows 11; fall back to PowerShell CIM.
            ps = (
                "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe' or Name='msedge.exe'\" | "
                f"Where-Object {{ $_.CommandLine -like '*{marker}*' }} | "
                "Select-Object -ExpandProperty ProcessId"
            )
            try:
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                    capture_output=True, text=True, timeout=25,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                pids = [l.strip() for l in res.stdout.splitlines() if l.strip().isdigit()]
            except Exception:
                pids = []

        killed = 0
        for pid in pids:
            try:
                subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, timeout=10,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                killed += 1
            except Exception:
                pass
        if killed:
            logger.info(f"Cleared {killed} leftover browser process(es) holding the profile.")
            time.sleep(1.2)
            self._mark_clean_exit()
        return killed

    def _mark_clean_exit(self):
        """
        Force-killing Chromium leaves exit_type='Crashed' in the profile, so the
        next launch greets the user with 'Chromium didn't shut down correctly /
        Restore pages?'. Rewrite the two flags that drive that bubble.
        """
        prefs = self.profile_dir / "Default" / "Preferences"
        if not prefs.exists():
            return
        try:
            with open(prefs, "r", encoding="utf-8") as f:
                data = json.load(f)
            profile = data.setdefault("profile", {})
            profile["exit_type"] = "Normal"
            profile["exited_cleanly"] = True
            tmp = prefs.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, prefs)
        except Exception as e:
            logger.debug(f"Could not reset the profile exit state: {e}")

    def start(self, timeout: float = 120.0) -> bool:
        with self._start_lock:
            if self.is_alive:
                return True
            if self._thread and self._thread.is_alive():
                # Starting up right now -- just wait for it.
                self._ready.wait(timeout)
                return self.is_alive

            self._ready.clear()
            self._stopped.clear()
            self._shutdown = False
            self._start_error = None
            self._migrate_legacy_profile()
            self._kill_profile_owners()
            self._clear_stale_locks()
            self._mark_clean_exit()

            self._thread = threading.Thread(target=self._run, name="fb-browser", daemon=True)
            self._thread.start()

            if not self._ready.wait(timeout):
                if self._start_error:
                    raise SessionError(self._start_error)
                raise SessionError("Browser did not start within the timeout.")
            if self._start_error:
                raise SessionError(self._start_error)
            return True

    def _launch(self, p):
        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-notifications",
            "--disable-infobars",
            "--no-default-browser-check",
            "--no-first-run",
            "--disable-features=Translate,OptimizationHints",
            "--window-position=60,40",
            "--window-size=1460,940",
            "--hide-crash-restore-bubble",
            "--restore-last-session=false",
        ]
        common = dict(
            headless=False,
            args=args,
            viewport=None,
            locale="en-US",
            timezone_id="Asia/Karachi",
            ignore_default_args=["--enable-automation"],
        )

        attempts = [("chromium", {}), ("chrome", {"channel": "chrome"}), ("msedge", {"channel": "msedge"})]
        last_exc = None
        for kind, extra in attempts:
            try:
                ctx = p.chromium.launch_persistent_context(
                    user_data_dir=str(self.profile_dir), **common, **extra
                )
                self.browser_kind = kind
                logger.info(f"Browser session started ({kind}) on profile {self.profile_dir}")
                return ctx
            except Exception as ex:
                last_exc = ex
                logger.warning(f"Launch via '{kind}' failed: {ex}")
                # Almost always a leftover browser still holding the profile.
                if self._kill_profile_owners():
                    self._clear_stale_locks()
                    try:
                        ctx = p.chromium.launch_persistent_context(
                            user_data_dir=str(self.profile_dir), **common, **extra
                        )
                        self.browser_kind = kind
                        logger.info(f"Browser session started ({kind}) after clearing a stale profile lock.")
                        return ctx
                    except Exception as ex2:
                        last_exc = ex2
                self._clear_stale_locks()
                time.sleep(0.6)
        raise SessionError(
            "Could not open the automation browser. Close any leftover "
            f"'Facebook Zenith Cleaner' browser window and try again. ({last_exc})"
        )

    def _run(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            self._start_error = f"Playwright is not installed: {e}"
            self._ready.set()
            return

        try:
            with sync_playwright() as p:
                try:
                    context = self._launch(p)
                except Exception as e:
                    self._start_error = str(e)
                    self._ready.set()
                    return

                context.set_default_timeout(20000)
                context.set_default_navigation_timeout(60000)
                page = context.pages[0] if context.pages else context.new_page()
                try:
                    page.add_init_script(
                        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
                    )
                except Exception:
                    pass

                # If the user closes the window, the whole session must end so the
                # next start() can relaunch it -- v1 kept failing every later job.
                closed = threading.Event()
                try:
                    context.on("close", lambda *_: closed.set())
                except Exception:
                    pass

                self._context = context
                self._page = page
                self._ready.set()

                while True:
                    job = self._jobs.get()
                    if job is None:
                        break
                    if closed.is_set():
                        job.error = SessionError("The browser window was closed.")
                        job.event.set()
                        break
                    try:
                        # The user may have closed just the tab; recover with a fresh one.
                        if page.is_closed():
                            page = context.pages[0] if context.pages else context.new_page()
                            self._page = page
                        job.result = job.fn(page, context)
                        self.last_error = None
                    except BaseException as e:  # noqa: BLE001 - surfaced to the caller
                        job.error = e
                        self.last_error = f"{type(e).__name__}: {e}"
                        logger.error(f"Browser job '{job.name}' failed: {e}")
                    finally:
                        job.event.set()

                    if closed.is_set():
                        logger.info("Browser window closed by the user; ending the session.")
                        break

                try:
                    context.close()
                except Exception:
                    pass
        except BaseException as e:  # noqa: BLE001
            self._start_error = str(e)
            self.last_error = str(e)
            logger.error(f"Browser session crashed: {e}")
            self._ready.set()
        finally:
            self._ready.clear()
            self._stopped.set()
            # Fail every queued job instead of leaving callers blocked forever.
            while True:
                try:
                    j = self._jobs.get_nowait()
                except queue.Empty:
                    break
                if j is not None:
                    j.error = SessionError("Browser session ended.")
                    j.event.set()

    def stop(self):
        if self._thread and self._thread.is_alive():
            self._shutdown = True
            self._jobs.put(None)
            self._thread.join(timeout=15)
        self._ready.clear()
        self._thread = None

    # -- job submission ----------------------------------------------------

    def submit_async(self, fn: Callable, name: str = "job") -> Job:
        self.start()
        job = Job(fn, name)
        self._jobs.put(job)
        return job

    def submit(self, fn: Callable, name: str = "job", timeout: Optional[float] = 180.0):
        return self.submit_async(fn, name).wait(timeout)

    @property
    def queue_depth(self) -> int:
        return self._jobs.qsize()


session = BrowserSession()


# ============================================================================
# SHARED PAGE HELPERS (run on the browser thread)
# ============================================================================

FB_HOME = "https://www.facebook.com"


def _cookie_user_id(context) -> Optional[str]:
    try:
        for c in context.cookies(FB_HOME):
            if c.get("name") == "c_user" and c.get("value"):
                return str(c["value"])
    except Exception:
        pass
    return None


def _goto(page, url: str, wait: str = "domcontentloaded", timeout: int = 60000) -> bool:
    try:
        page.goto(url, timeout=timeout, wait_until=wait)
        return True
    except Exception as e:
        logger.warning(f"Navigation to {url} failed: {e}")
        return False


def _goto_or_transient(page, url: str, timeout: int = 45000):
    """
    Navigate, distinguishing a dead browser (SessionError -> resume later) from a
    network hiccup (TransientError -> pause and retry). A page that simply has no
    such profile still 'loads', so only real transport failures raise here.
    """
    try:
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        return
    except Exception as e:
        msg = str(e).lower()
        if page.is_closed() or "closed" in msg or "crash" in msg or "target" in msg:
            raise SessionError(f"Browser closed while opening {url}: {e}")
        # net::ERR_INTERNET_DISCONNECTED, timeouts, DNS, TLS resets, etc.
        raise TransientError(f"Could not reach {url}: {e}")


def _wait_for_main(page, timeout: float = 12.0) -> bool:
    """Wait for the list container instead of sleeping a fixed 2.4s every load."""
    try:
        page.wait_for_selector('div[role="main"]', timeout=int(timeout * 1000))
        return True
    except Exception:
        return False


# Height of whatever actually scrolls -- FB puts these lists in an INNER
# overflow container, so document.body.scrollHeight frequently never moves even
# as hundreds of rows load. Measuring the max of the body and the real scroll
# container is what makes "did new content arrive?" reliable.
MEASURE_JS = r"""
() => {
  const main = document.querySelector('div[role="main"]');
  let best = document.body ? document.body.scrollHeight : 0;
  if (main) {
    const cands = [main, ...main.querySelectorAll('div')].slice(0, 400);
    for (const c of cands) {
      if (c.scrollHeight > c.clientHeight + 200 && c.clientHeight > 300) {
        const st = getComputedStyle(c);
        if (st.overflowY === 'auto' || st.overflowY === 'scroll') {
          best = Math.max(best, c.scrollHeight);
          break;
        }
      }
    }
  }
  return best;
}
"""


def _measure_height(page) -> int:
    try:
        return int(page.evaluate(MEASURE_JS) or 0)
    except Exception:
        return -1        # signals "could not measure" to the caller


def _scroll_and_grow(page, prev_height: int, settle: float = 2.5) -> int:
    """
    Scroll the virtualized list and return the moment new content actually
    arrives, instead of blind-sleeping a flat interval. Measures the real scroll
    container (not just body), so growth is detected on every FB layout. Returns
    the current height; == prev_height means nothing new loaded within `settle`s.
    """
    try:
        page.evaluate(SCROLL_JS)
    except Exception:
        return prev_height
    deadline = time.time() + settle
    last = prev_height
    while time.time() < deadline:
        h = _measure_height(page)
        if h < 0:
            return prev_height
        if h > prev_height:
            return h
        last = h
        time.sleep(0.2)
    return last


# Signs that Facebook has thrown a security wall rather than the real page.
_BLOCK_URL_MARKERS = ("/checkpoint", "/checkpoint/", "checkpoint/block", "/captcha", "/challenge")
# Kept deliberately specific -- phrases that essentially only appear on a block /
# checkpoint wall, so a friend's post text can't trip a false stop. The URL
# markers above are the primary, near-zero-false-positive signal.
_BLOCK_TEXT_MARKERS = (
    "temporarily blocked", "you're temporarily blocked", "you’re temporarily blocked",
    "we limit how often", "confirm your identity to continue",
    "you can't use this feature", "you’re unable to use this feature",
    "آپ عارضی طور پر بلاک",
)


def _detect_block(page) -> str:
    """Return a short reason if the page is a checkpoint/block wall, else ''."""
    try:
        url = (page.url or "").lower()
    except Exception:
        url = ""
    if any(m in url for m in _BLOCK_URL_MARKERS):
        return "Facebook security checkpoint"
    try:
        body = (page.evaluate("() => (document.body && document.body.innerText || '').slice(0, 4000)") or "").lower()
    except Exception:
        return ""
    for m in _BLOCK_TEXT_MARKERS:
        if m in body:
            return "Facebook rate-limit / block screen"
    return ""


def _dismiss_overlays(page):
    """Closes cookie banners and stray dialogs that swallow clicks."""
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    for label in ("Allow all cookies", "Accept all", "Only allow essential cookies", "Close"):
        try:
            loc = page.locator(f'[aria-label="{label}"]').first
            if loc.count() > 0 and loc.is_visible():
                loc.click(timeout=1500)
                time.sleep(0.4)
                return
        except Exception:
            continue


def _click(loc, timeout: int = 4000) -> bool:
    """Scroll-into-view + real click, falling back to a dispatched click."""
    try:
        loc.scroll_into_view_if_needed(timeout=2500)
    except Exception:
        pass
    try:
        loc.click(timeout=timeout)
        return True
    except Exception:
        pass
    try:
        loc.click(timeout=timeout, force=True)
        return True
    except Exception:
        pass
    try:
        loc.dispatch_event("click")
        return True
    except Exception:
        return False


FIND_ACTION_BUTTON_JS = r"""(args) => {
  const labels = args.texts.map(t => String(t).trim().toLowerCase());
  const inChrome = (el) => !!el.closest('[role="navigation"], [role="banner"], nav, [role="menubar"]');
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 8 && r.height > 8;
  };
  const match = (el) => {
    const al = (el.getAttribute('aria-label') || '').trim().toLowerCase();
    if (al && labels.includes(al)) return true;
    if (el.children.length > 3) return false;
    const t = (el.innerText || '').trim().toLowerCase();
    return !!t && labels.includes(t);
  };

  const all = Array.from(document.querySelectorAll(
    '[aria-label], div[role="button"], button, a[role="button"]'));
  const cands = all.filter(el => visible(el) && !inChrome(el) && match(el));
  if (!cands.length) return null;

  // A profile has two "Friends" elements: the action-bar control that opens the
  // friendship popup, and the profile's Friends tab. Only the former declares
  // aria-haspopup, so it wins whenever one exists.
  if (args.preferPopup) {
    const withPopup = cands.find(el => el.hasAttribute('aria-haspopup')
                                    || el.closest('[aria-haspopup]'));
    if (withPopup) return withPopup;
    if (args.requirePopup) return null;
  }
  return cands[0];
}"""


def _find_button(page, texts: List[str], root=None, exact_aria: bool = False,
                 prefer_popup: bool = False, require_popup: bool = False):
    """
    Returns the first visible clickable element whose aria-label or text matches
    any of `texts`, ignoring anything inside the site chrome (top bar, left nav,
    profile tab strip). Values never get interpolated into a selector string, so
    names containing quotes cannot break the query.
    """
    if root is not None:
        # Scoped lookups (confirm dialogs) stay on plain locators.
        for txt in texts:
            try:
                loc = root.locator(f'[aria-label="{txt}"]').first
                if loc.count() > 0 and loc.is_visible():
                    return loc
            except Exception:
                pass
        for txt in texts:
            for sel in ('div[role="button"]', "button", 'a[role="button"]'):
                try:
                    loc = root.locator(sel).filter(
                        has_text=re.compile(rf"^\s*{re.escape(txt)}\s*$", re.I)).first
                    if loc.count() > 0 and loc.is_visible():
                        return loc
                except Exception:
                    continue
        return None

    try:
        handle = page.evaluate_handle(FIND_ACTION_BUTTON_JS, {
            "texts": texts, "preferPopup": prefer_popup, "requirePopup": require_popup,
        })
        return handle.as_element()
    except Exception:
        return None


# Facebook's friendship / page popups are NOT role="menu" with role="menuitem"
# children. The "Friends" control declares aria-haspopup="dialog" and the entries
# ("Unfollow", "Unfriend", "Leave group", ...) are plain <div>s inside it. Matching
# only [role="menuitem"] found nothing, which is why every real removal failed with
# "no Unfriend entry in the menu" while the synthetic fixture passed.
FIND_POPUP_ITEM_JS = r"""(args) => {
  const want = String(args.text).trim().toLowerCase();
  const roots = document.querySelectorAll(args.rootSelector);
  for (const root of roots) {
    for (const n of root.querySelectorAll('*')) {
      if (n.children.length > 1) continue;                 // leaf-ish node
      const t = (n.innerText || n.textContent || '').trim().toLowerCase();
      if (t !== want) continue;
      const r = n.getBoundingClientRect();
      if (r.width < 4 || r.height < 4) continue;           // must be visible
      // Climb to the nearest thing that actually handles the click.
      let c = n;
      for (let i = 0; i < 5 && c && c !== root; i++) {
        const role = c.getAttribute('role');
        if (role === 'menuitem' || role === 'menuitemradio' || role === 'button'
            || c.tagName === 'BUTTON' || c.tagName === 'A') return c;
        c = c.parentElement;
      }
      return n;
    }
  }
  return null;
}"""


def _click_popup_item(page, texts: List[str], root_selector: str, timeout: float = 8.0) -> bool:
    """Clicks an entry inside an open popup, whatever markup Facebook used for it."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for txt in texts:
            try:
                handle = page.evaluate_handle(
                    FIND_POPUP_ITEM_JS, {"text": txt, "rootSelector": root_selector}
                )
                element = handle.as_element()
                if element is not None:
                    try:
                        element.scroll_into_view_if_needed(timeout=2000)
                    except Exception:
                        pass
                    try:
                        element.click(timeout=4000)
                        return True
                    except Exception:
                        try:
                            element.click(timeout=3000, force=True)
                            return True
                        except Exception:
                            pass
            except Exception:
                continue
        time.sleep(0.4)
    return False


def _click_menu_item(page, texts: List[str], timeout: float = 8.0) -> bool:
    """An entry in the popup opened by a profile / group / page action button."""
    return _click_popup_item(
        page, texts, '[role="menu"], [role="dialog"], [role="listbox"]', timeout
    )


def _click_dialog_button(page, texts: List[str], timeout: float = 8.0) -> bool:
    """Confirms a modal. Never blind-clicks 'the last button' -- that used to hit Cancel."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            dialog = page.locator('div[role="dialog"]').last
            if dialog.count() > 0:
                btn = _find_button(page, texts, root=dialog)
                if btn is not None and _click(btn):
                    return True
        except Exception:
            pass
        # Confirm buttons are sometimes plain divs too.
        if _click_popup_item(page, texts, '[role="dialog"]', timeout=1.0):
            return True
        time.sleep(0.3)
    return False


def _human_pause(a: float = 0.6, b: float = 1.3):
    time.sleep(random.uniform(a, b))


# ---------------------------------------------------------------------------
# Extraction JS. One collector, parameterised per category.
# `profile.php?id=NNN` links keep their query string -- stripping it collapsed
# every such friend onto a single id and silently deleted them all.
# ---------------------------------------------------------------------------

COLLECT_JS = r"""
(cfg) => {
  const RESERVED = new Set(['profile.php','friends','groups','pages','watch','marketplace','gaming',
    'events','saved','memories','settings','help','policies','notifications','messages','bookmarks',
    'me','home.php','login.php','business','ads','adsmanager','allactivity','privacy','terms','reel',
    'reels','stories','story.php','photo','photo.php','permalink.php','sharer','sharer.php','l.php',
    'hashtag','search','live','games','marketplace','video.php','media','directory','pages_manager',
    'gaming','fundraisers','jobs','weather','climatescience','lite','plugins','dialog','recover',
    'checkpoint','confirmemail.php','watchparty','birthdays','friends_all','campaign',
    'login','login.php','reg','signup','r.php','recover.php','cookies','careers','developers',
    'about','terms.php','policy.php','privacy_policy','legal','ads','adchoices','contact',
    'messenger','instagram','threads','whatsapp','oculus','meta','metaai','facebooklite',
    'gaming.php','watch.php','biz','business.php','pages_manager','marketplace.php',
    'professional_dashboard','allactivity.php','notes','bookmarks','story.php']);

  const normProfile = (raw) => {
    if (!raw) return null;
    let u;
    try { u = new URL(raw, location.origin); } catch (e) { return null; }
    if (!/(^|\.)facebook\.com$/i.test(u.hostname)) return null;

    let path = u.pathname.replace(/\/+$/, '');
    if (path.startsWith('/')) path = path.slice(1);

    if (path === 'profile.php') {
      const id = u.searchParams.get('id');
      if (!id || !/^\d+$/.test(id)) return null;
      return 'https://www.facebook.com/profile.php?id=' + id;
    }
    if (!path || path.includes('/')) return null;         // only top-level vanity URLs
    if (RESERVED.has(path.toLowerCase())) return null;
    if (/^\d+$/.test(path)) return null;                  // bare numeric == post id, not a profile
    return 'https://www.facebook.com/' + path;
  };

  const normGroup = (raw) => {
    if (!raw) return null;
    let u;
    try { u = new URL(raw, location.origin); } catch (e) { return null; }
    if (!/(^|\.)facebook\.com$/i.test(u.hostname)) return null;
    const m = u.pathname.match(/^\/groups\/([^\/]+)\/?$/);
    if (!m) return null;
    const slug = m[1];
    if (['feed','joins','discover','create','browse','your_groups','invites'].includes(slug.toLowerCase())) return null;
    return 'https://www.facebook.com/groups/' + slug;
  };

  const norm = cfg.kind === 'group' ? normGroup : normProfile;

  const main = document.querySelector('div[role="main"]') || document.body;
  const anchors = Array.from(main.querySelectorAll('a[href]'));
  const byUrl = new Map();

  for (const a of anchors) {
    const url = norm(a.getAttribute('href') || a.href);
    if (!url) continue;

    // The row/card that owns this link -- used for the name, avatar and state text.
    let card = a;
    for (let i = 0; i < 5 && card.parentElement; i++) {
      const p = card.parentElement;
      if (p === main) break;
      card = p;
      if (card.getAttribute('role') === 'listitem' || card.getAttribute('role') === 'gridcell') break;
    }

    let name = (a.getAttribute('aria-label') || '').trim();
    if (!name) name = (a.innerText || '').trim().split('\n')[0].trim();
    if (!name) {
      const img = a.querySelector('img[alt]');
      if (img) name = (img.getAttribute('alt') || '').replace(/'s profile picture$/i, '').trim();
    }

    let avatar = '';
    const img = a.querySelector('img') || card.querySelector('img');
    if (img && img.src && img.src.startsWith('http') && !img.src.includes('data:image/svg')) avatar = img.src;

    const cardText = (card.innerText || '').trim();

    const prev = byUrl.get(url);
    if (!prev) {
      byUrl.set(url, { url, name, avatar, cardText });
    } else {
      if (!prev.name && name) prev.name = name;
      if (!prev.avatar && avatar) prev.avatar = avatar;
      if (cardText.length > prev.cardText.length) prev.cardText = cardText;
    }
  }

  const out = [];
  for (const v of byUrl.values()) {
    if (!v.name) continue;
    if (v.name.length < 2 || v.name.length > 90) continue;
    if (v.name.includes('\n')) continue;
    if (cfg.requireAvatar && !v.avatar) continue;
    out.push({ id: v.url, url: v.url, name: v.name, avatar: v.avatar,
               cardText: v.cardText.slice(0, 400), type: cfg.kind, selected: true });
  }
  return out;
}
"""

SCROLL_JS = r"""
() => {
  // Facebook virtualises these lists inside a scroll container, not the window.
  const main = document.querySelector('div[role="main"]');
  let el = null;
  const candidates = main ? [main, ...main.querySelectorAll('div')] : [];
  for (const c of candidates.slice(0, 400)) {
    if (c.scrollHeight > c.clientHeight + 200 && c.clientHeight > 300) {
      const st = getComputedStyle(c);
      if (st.overflowY === 'auto' || st.overflowY === 'scroll') { el = c; break; }
    }
  }
  if (el) {
    el.scrollTop = el.scrollHeight;
  }
  window.scrollTo(0, document.body.scrollHeight);
  return document.body.scrollHeight;
}
"""


# ============================================================================
# ENGINE
# ============================================================================

# Several source URLs per category: Facebook splits "pages you liked" and
# "pages you follow" across two tabs, and scanning only the first missed
# everything the user follows without having liked.
CATEGORY_URLS = {
    "friends": [f"{FB_HOME}/me/friends"],
    "groups": [f"{FB_HOME}/groups/joins"],
    "pages": [f"{FB_HOME}/pages/?category=liked", f"{FB_HOME}/pages/?category=following"],
}

SINGULAR = {"friends": "friend", "groups": "group", "pages": "page"}
PLURAL = {"friend": "friends", "group": "groups", "page": "pages"}


class FacebookEngine:
    def __init__(self):
        self.is_scanning = False
        self.should_stop_scan = False
        self.is_purging = False
        self.should_stop_purge = False

        self.owner_id: Optional[str] = None
        self.owner_url: Optional[str] = None
        self.owner_name: Optional[str] = None

        self.last_error: Optional[str] = None

        self.scan_info: Dict[str, Any] = {
            "is_scanning": False,
            "stage": "idle",
            "message": "Ready",
            "current_count": 0,
            "category": "all",
        }

        self.data: Dict[str, Any] = {
            "friends": [],
            "groups": [],
            "pages": [],
            "last_scan_time": None,
        }

        self.purge_progress: Dict[str, Any] = self._blank_progress()

        self._lock = threading.RLock()
        self._resumable_pending = 0        # cached so /api/status never reads disk
        self.load_cached_data()

        # A purge that was cut off by a crash / power loss / closed browser leaves
        # a parked queue on disk. Flag it so the dashboard can offer Resume.
        self._resumable_pending = sum(
            1 for i in self.load_pending_queue() if i.get("status") == "pending"
        )
        if self._resumable_pending:
            self.purge_progress["resumable"] = True
            logger.info(f"Found a parked purge queue: {self._resumable_pending} item(s) resumable.")

    # -- progress ----------------------------------------------------------

    @staticmethod
    def _blank_progress() -> Dict[str, Any]:
        return {
            "is_running": False,
            "current_action": "Idle",
            "total_items": 0,
            "processed_items": 0,
            "successful_items": 0,
            "failed_items": 0,
            "skipped_items": 0,
            "current_item_name": "",
            "current_item_type": "",
            "log": [],
            "start_time": None,
            "elapsed_seconds": 0,
            "finished": False,
            "paused": False,          # True while waiting out an internet/browser interruption
            "resumable": False,       # True when an unfinished queue is parked on disk
            "blocked": False,         # True when Facebook threw a checkpoint / rate-limit wall
        }

    def progress_snapshot(self) -> Dict[str, Any]:
        """Deep-ish copy so a JSON response can never race the purge thread's list writes."""
        with self._lock:
            snap = dict(self.purge_progress)
            snap["log"] = list(self.purge_progress.get("log", []))
            return snap

    def _log_event(self, status: str, text: str):
        entry = {"time": time.strftime("%H:%M:%S"), "status": status, "text": text}
        with self._lock:
            self.purge_progress["log"].insert(0, entry)
            del self.purge_progress["log"][150:]
        logger.info(f"[purge:{status}] {text}")

    # -- cache -------------------------------------------------------------

    def load_cached_data(self):
        with self._lock:
            if not DATA_CACHE_FILE.exists():
                return
            try:
                with open(DATA_CACHE_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
            except Exception as e:
                logger.error(f"Cache unreadable ({e}); starting empty.")
                return
            if not isinstance(loaded, dict):
                return
            for key in ("friends", "groups", "pages"):
                self.data[key] = self._sanitize_items(loaded.get(key, []), SINGULAR[key])
            self.data["last_scan_time"] = loaded.get("last_scan_time")
            self.owner_id = loaded.get("owner_id") or self.owner_id
            self.owner_url = loaded.get("owner_url") or self.owner_url
            self.owner_name = loaded.get("owner_name") or self.owner_name

    def save_cached_data(self):
        with self._lock:
            payload = {
                "friends": self.data["friends"],
                "groups": self.data["groups"],
                "pages": self.data["pages"],
                "last_scan_time": self.data["last_scan_time"],
                "owner_id": self.owner_id,
                "owner_url": self.owner_url,
                "owner_name": self.owner_name,
            }
            tmp = DATA_CACHE_FILE.with_suffix(".tmp")
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
                os.replace(tmp, DATA_CACHE_FILE)
            except Exception as e:
                logger.error(f"Could not save cache: {e}")

    # -- owner protection --------------------------------------------------

    def is_protected_owner(self, name: str = "", url: str = "") -> bool:
        """
        True only for the signed-in account itself. Identity comes from the c_user
        cookie and the resolved profile URL -- never from a name blacklist, which
        used to silently delete every friend sharing the owner's first name.
        """
        u = (url or "").strip().lower().rstrip("/")
        if not u:
            return False
        if self.owner_id and (f"id={self.owner_id}" in u or u.endswith(f"/{self.owner_id}")):
            return True
        if self.owner_url and u == self.owner_url.strip().lower().rstrip("/"):
            return True
        return False

    # -- sanitation --------------------------------------------------------

    def _sanitize_items(self, items: Any, item_type: str) -> List[Dict[str, Any]]:
        if not isinstance(items, list):
            return []
        cleaned: List[Dict[str, Any]] = []
        seen: Set[str] = set()

        for it in items:
            if not isinstance(it, dict):
                continue
            name = (it.get("name") or "").strip()
            url = (it.get("url") or "").strip()
            if not name or not url:
                continue
            if len(name) < 2 or len(name) > 90 or "\n" in name:
                continue

            norm = normalize_text(name)
            if norm in EXCLUDED_HEADINGS:
                continue
            if self.is_protected_owner(name, url):
                continue

            key = url.lower().rstrip("/")
            if key in seen:
                continue
            seen.add(key)

            cleaned.append({
                "id": url,
                "name": name,
                "url": url,
                "avatar": it.get("avatar") or "",
                "subText": it.get("subText") or "",
                "type": it.get("type") or item_type,
                "selected": bool(it.get("selected", True)),
            })
        return cleaned

    # -- session / auth ----------------------------------------------------

    def open_browser_for_user(self) -> Dict[str, Any]:
        """Starts (or reuses) the one browser window and parks it on Facebook."""
        if self.is_scanning or self.is_purging:
            focus_browser_window(min_interval=0.0)
            return {"success": True, "message": "The browser window is already open and working."}
        try:
            session.start()
        except Exception as e:
            self.last_error = str(e)
            return {"success": False, "message": f"Could not start the browser: {e}"}

        def _job(page, ctx):
            if "facebook.com" not in (page.url or ""):
                _goto(page, FB_HOME)
            _dismiss_overlays(page)
            try:
                page.bring_to_front()
            except Exception:
                pass
            focus_browser_window()
            return True

        try:
            session.submit(_job, "open-browser", timeout=90)
            self.last_error = None
            return {"success": True, "message": "Browser window is open. Log into Facebook if prompted."}
        except Exception as e:
            self.last_error = str(e)
            return {"success": False, "message": str(e)}

    def _resolve_owner(self, page, ctx) -> Dict[str, Any]:
        """Reads c_user and the canonical profile URL so we know who not to remove."""
        uid = _cookie_user_id(ctx)
        if not uid:
            return {"authenticated": False}

        self.owner_id = uid
        if not self.owner_url:
            try:
                current = page.url
                _goto(page, f"{FB_HOME}/me/", timeout=30000)
                time.sleep(1.2)
                resolved = page.url.split("?")[0].rstrip("/")
                if "facebook.com" in resolved and "/me" not in resolved:
                    self.owner_url = resolved
                try:
                    # page.title() is "(13) Facebook" when notifications are pending,
                    # so read the profile heading / og:title instead.
                    name = page.evaluate(
                        r"""() => {
                            const og = document.querySelector('meta[property="og:title"]');
                            if (og && og.content) return og.content.trim();
                            const h1 = document.querySelector('div[role="main"] h1');
                            if (h1 && h1.innerText) return h1.innerText.trim();
                            return (document.title || '').replace(/^\(\d+\)\s*/, '').split('|')[0].trim();
                        }"""
                    )
                    if name and name.lower() not in ("facebook", ""):
                        self.owner_name = name
                except Exception:
                    pass
                if current and "about:blank" not in current:
                    _goto(page, current, timeout=30000)
            except Exception as e:
                logger.debug(f"Owner resolution partial: {e}")
        return {"authenticated": True, "userId": uid, "userUrl": self.owner_url, "userName": self.owner_name}

    def check_login_status(self) -> Dict[str, Any]:
        """Real auth check via the c_user cookie -- no more guessing from file sizes."""
        if not session.is_alive:
            return {
                "authenticated": False,
                "sessionOpen": False,
                "userName": "Browser Closed",
                "message": "Click 'Open Browser' to start the Facebook window and log in.",
            }

        # Jobs run one at a time on the browser thread. Probing during a scan or
        # purge would sit in the queue for minutes and then navigate the page out
        # from under the running job, so answer from what we already know.
        if self.is_scanning or self.is_purging:
            busy = "scan" if self.is_scanning else "purge"
            return {
                "authenticated": bool(self.owner_id),
                "sessionOpen": True,
                "userId": self.owner_id,
                "userName": self.owner_name or ("Active Session" if self.owner_id else "Login Required"),
                "userUrl": self.owner_url,
                "message": f"Browser is busy running a {busy}.",
            }

        def _job(page, ctx):
            uid = _cookie_user_id(ctx)
            if not uid:
                return {"authenticated": False}
            return self._resolve_owner(page, ctx)

        try:
            res = session.submit(_job, "auth-check", timeout=60)
        except Exception as e:
            self.last_error = str(e)
            return {
                "authenticated": False, "sessionOpen": session.is_alive,
                "userName": "Session Error", "message": str(e),
            }

        if res.get("authenticated"):
            with self._lock:
                self.save_cached_data()
            return {
                "authenticated": True,
                "sessionOpen": True,
                "userId": res.get("userId"),
                "userName": res.get("userName") or "Active Session",
                "userUrl": res.get("userUrl"),
                "message": "Facebook session is active.",
            }
        return {
            "authenticated": False,
            "sessionOpen": True,
            "userName": "Login Required",
            "message": "Log into Facebook in the open browser window.",
        }

    def _ensure_authenticated(self, page, ctx, wait_seconds: int = 240) -> bool:
        """Blocks (on the browser thread) until c_user exists, or the user cancels."""
        if _cookie_user_id(ctx):
            self._resolve_owner(page, ctx)
            return True

        if "facebook.com" not in (page.url or ""):
            _goto(page, FB_HOME)

        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            if self.should_stop_scan or self.should_stop_purge:
                return False
            if _cookie_user_id(ctx):
                self._resolve_owner(page, ctx)
                with self._lock:
                    self.scan_info["stage"] = "authenticated"
                    self.scan_info["message"] = "Signed in. Starting extraction..."
                return True
            with self._lock:
                self.scan_info["stage"] = "waiting_login"
                self.scan_info["message"] = "Waiting for you to log into Facebook in the browser window..."
            focus_browser_window()
            time.sleep(2.0)

        self.last_error = "Timed out waiting for Facebook login."
        return False

    # -- scanning ----------------------------------------------------------

    def stop_scan(self):
        with self._lock:
            if self.is_scanning:
                self.should_stop_scan = True
                self.scan_info["message"] = "Stopping scan..."
            logger.info("Stop-scan signal received.")

    def _collect_category(self, page, category: str, max_scrolls: int, max_items: int) -> List[Dict[str, Any]]:
        kind = SINGULAR[category]
        found: Dict[str, Dict[str, Any]] = {}
        # Only the friends list needs the avatar heuristic to shake off nav links.
        # Groups and Pages render their thumbnails without <img>, so requiring one
        # silently returned zero results.
        cfg = {"kind": kind, "requireAvatar": category == "friends"}

        for source in CATEGORY_URLS[category]:
            if self.should_stop_scan:
                break
            self._collect_from_url(page, source, cfg, category, found, max_scrolls, max_items)
        return list(found.values())

    def _collect_from_url(self, page, target: str, cfg: Dict[str, Any], category: str,
                          found: Dict[str, Dict[str, Any]], max_scrolls: int, max_items: int):
        # Pause (not fail) if the internet is down when the list opens.
        for _ in range(3):
            if self.should_stop_scan:
                return
            try:
                _goto_or_transient(page, target, timeout=60000)
                break
            except TransientError:
                if not self._wait_for_connection(page, "scan", label="opening list"):
                    return
        else:
            raise SessionError(f"Could not open {target}")

        _dismiss_overlays(page)
        _wait_for_main(page)            # event-based, replaces a flat 2.4s sleep

        stale_rounds = 0
        prev_count = -1
        prev_height = 0

        for i in range(max_scrolls):
            if self.should_stop_scan:
                break
            try:
                batch = page.evaluate(COLLECT_JS, cfg)
            except Exception as e:
                logger.warning(f"Extraction pass {i + 1} failed: {e}")
                batch = []

            for raw in batch:
                url = raw.get("url")
                if not url or url in found:
                    continue
                if self.is_protected_owner(raw.get("name", ""), url):
                    continue
                if normalize_text(raw.get("name", "")) in EXCLUDED_HEADINGS:
                    continue

                card_text = (raw.pop("cardText", "") or "").lower()
                if category == "friends" and any(m in card_text for m in NON_FRIEND_MARKERS):
                    continue  # a suggestion / pending request, not an actual friend

                if category == "friends":
                    m = re.search(r"(\d+)\s+(mutual friends?|مشترکہ دوست)", card_text, re.I)
                    raw["subText"] = m.group(0) if m else ""
                found[url] = raw

            count = len(found)
            with self._lock:
                self.scan_info["current_count"] = count
                self.scan_info["message"] = f"Found {count} {category} (pass {i + 1}/{max_scrolls})..."
            logger.info(f"[{category}] pass {i + 1}/{max_scrolls} -> {count}")

            if max_items and count >= max_items:
                break

            # Scroll and return the moment new content arrives. The end of a list
            # is reached only when BOTH the count and the document height have
            # stopped moving -- height alone catches items still rendering, count
            # alone catches trailing filler. Four quiet rounds ends it (was 8 flat
            # 1.5s sleeps = ~12s of dead time at the end of every list).
            new_height = _scroll_and_grow(page, prev_height, settle=2.5)
            if count == prev_count and new_height == prev_height:
                stale_rounds += 1
                if stale_rounds >= 3:
                    logger.info(f"[{category}] settled after {stale_rounds} quiet passes -- {count} found.")
                    break
            else:
                stale_rounds = 0
            prev_count = count
            prev_height = new_height
            # Small human-ish jitter between passes; _scroll_and_grow already
            # absorbed the real wait, so this stays short.
            self._sleep_interruptible(random.uniform(0.3, 0.6), "scan")

    def _run_scan(self, categories: List[str]) -> Dict[str, Any]:
        with self._lock:
            if self.is_scanning:
                return {"success": False, "message": "A scan is already running."}
            if self.is_purging:
                return {"success": False, "message": "Cannot scan while a purge is running."}
            self.is_scanning = True
            self.should_stop_scan = False
            self.last_error = None
            self.scan_info = {
                "is_scanning": True,
                "stage": "initializing",
                "message": "Opening the Facebook browser window...",
                "current_count": 0,
                "category": categories[0] if len(categories) == 1 else "all",
            }

        def _job(page, ctx):
            if not self._ensure_authenticated(page, ctx):
                return {"success": False, "message": self.last_error or "Login required."}

            results: Dict[str, List[Dict[str, Any]]] = {}
            partial: Set[str] = set()
            for cat in categories:
                if self.should_stop_scan:
                    break
                with self._lock:
                    self.scan_info["stage"] = cat
                    self.scan_info["category"] = cat
                    self.scan_info["current_count"] = 0
                    self.scan_info["message"] = f"Scanning {cat}..."
                # Generous ceilings; the "no new items in 5 passes" check is what
                # actually ends a scan, so these only bound pathological cases.
                limits = {"friends": (250, 0), "groups": (150, 0), "pages": (150, 0)}[cat]
                results[cat] = self._collect_category(page, cat, max_scrolls=limits[0], max_items=limits[1])
                if self.should_stop_scan:
                    partial.add(cat)      # cut short -- the result is incomplete
                time.sleep(1.2)

            with self._lock:
                for cat, items in results.items():
                    fresh = self._merge_preserving_choices(cat, self._sanitize_items(items, SINGULAR[cat]))
                    if cat in partial:
                        # A cancelled scan must never delete a list the user already
                        # has: fold in whatever was found and keep the rest.
                        existing = {i["url"].lower().rstrip("/"): i for i in self.data.get(cat, [])}
                        for item in fresh:
                            existing.setdefault(item["url"].lower().rstrip("/"), item)
                        self.data[cat] = list(existing.values())
                    else:
                        self.data[cat] = fresh
                if not partial:
                    self.data["last_scan_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
                self.save_cached_data()
                counts = {c: len(self.data[c]) for c in ("friends", "groups", "pages")}

            return {"success": True, "counts": counts, "stopped": self.should_stop_scan}

        try:
            return session.submit(_job, f"scan-{'+'.join(categories)}", timeout=3600)
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Scan failed: {e}")
            return {"success": False, "message": str(e)}
        finally:
            with self._lock:
                self.is_scanning = False
                stopped = self.should_stop_scan
                self.scan_info["is_scanning"] = False
                self.scan_info["stage"] = "idle"
                self.scan_info["message"] = "Scan stopped." if stopped else "Scan complete."

    def _merge_preserving_choices(self, category: str, fresh: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """A rescan must not silently re-check items the user deliberately unchecked."""
        prior = {i["url"].lower().rstrip("/"): i.get("selected", True) for i in self.data.get(category, [])}
        for item in fresh:
            key = item["url"].lower().rstrip("/")
            if key in prior:
                item["selected"] = prior[key]
        return fresh

    def scan_all_full(self) -> Dict[str, Any]:
        return self._run_scan(["friends", "groups", "pages"])

    def scan_single_category(self, category: str) -> Dict[str, Any]:
        if category not in CATEGORY_URLS:
            return {"success": False, "message": f"Unknown category: {category}"}
        return self._run_scan([category])

    # -- removal flows -----------------------------------------------------

    def _unfriend(self, page, item: Dict[str, Any]) -> tuple[bool, str]:
        name, url = item.get("name", "Friend"), item.get("url", "")
        if not url:
            return False, "no profile url"
        _goto_or_transient(page, url, timeout=45000)   # raises on net loss -> pause+retry
        _dismiss_overlays(page)
        blocked = _detect_block(page)
        if blocked:
            raise BlockedError(blocked)
        _human_pause(1.6, 2.4)

        add_btn = _find_button(page, T["add_friend"])
        friends_btn = _find_button(page, T["friends_btn"], prefer_popup=True)
        if add_btn is not None and friends_btn is None:
            return True, "already not a friend"
        if friends_btn is None:
            more = _find_button(page, T["more"])
            if more is not None and _click(more):
                _human_pause(0.6, 1.0)
                friends_btn = _find_button(page, T["friends_btn"], prefer_popup=True)
        if friends_btn is None:
            return False, "friendship button not found"

        if not _click(friends_btn):
            return False, "could not open the friendship menu"
        if not _click_menu_item(page, T["unfriend"]):
            page.keyboard.press("Escape")
            return False, "no Unfriend entry in the menu"
        _human_pause(0.7, 1.1)
        if not _click_dialog_button(page, T["unfriend"] + T["confirm"]):
            page.keyboard.press("Escape")
            return False, "confirmation dialog not confirmed"

        _human_pause(1.4, 2.2)
        # Verify: an "Add friend" button must now be present.
        for _ in range(6):
            if _find_button(page, T["add_friend"]) is not None:
                return True, "unfriended"
            time.sleep(0.8)
        return False, "removal not confirmed by the page"

    def _leave_group(self, page, item: Dict[str, Any]) -> tuple[bool, str]:
        name, url = item.get("name", "Group"), item.get("url", "")
        if not url:
            return False, "no group url"
        _goto_or_transient(page, url, timeout=45000)
        _dismiss_overlays(page)
        blocked = _detect_block(page)
        if blocked:
            raise BlockedError(blocked)
        _human_pause(1.8, 2.6)

        joined = _find_button(page, T["joined"], prefer_popup=True)
        if joined is None and _find_button(page, T["join"]) is not None:
            return True, "already left"

        opened = False
        if joined is not None and _click(joined):
            opened = _click_menu_item(page, T["leave_group"], timeout=5)
        if not opened:
            more = _find_button(page, T["more"])
            if more is not None and _click(more):
                opened = _click_menu_item(page, T["leave_group"], timeout=5)
        if not opened:
            page.keyboard.press("Escape")
            return False, "no 'Leave group' entry found"

        _human_pause(0.8, 1.2)
        if not _click_dialog_button(page, T["leave_group"] + T["confirm"]):
            page.keyboard.press("Escape")
            return False, "leave confirmation not accepted"

        _human_pause(1.6, 2.4)
        # Verify honestly: a "Join" control must be back and "Joined" gone. If the
        # page can't confirm, report failure -- the one retry re-navigates and, if
        # the leave really went through, sees "Join" and returns "already left".
        for _ in range(6):
            if _find_button(page, T["join"]) is not None and _find_button(page, T["joined"]) is None:
                return True, "left group"
            time.sleep(0.8)
        return False, "leave not confirmed by the page"

    def _unfollow_page(self, page, item: Dict[str, Any]) -> tuple[bool, str]:
        url = item.get("url", "")
        if not url:
            return False, "no page url"
        _goto_or_transient(page, url, timeout=45000)
        _dismiss_overlays(page)
        blocked = _detect_block(page)
        if blocked:
            raise BlockedError(blocked)
        _human_pause(1.8, 2.6)

        following = _find_button(page, T["following"], prefer_popup=True)
        liked = _find_button(page, T["liked"], prefer_popup=True)
        if following is None and liked is None:
            if _find_button(page, T["follow"]) is not None or _find_button(page, T["like"]) is not None:
                return True, "already unfollowed"
            return False, "follow state not found"

        did = []
        if following is not None and _click(following):
            if _click_menu_item(page, T["unfollow"], timeout=5):
                did.append("unfollowed")
                _human_pause(0.9, 1.4)
            else:
                page.keyboard.press("Escape")

        liked = _find_button(page, T["liked"], prefer_popup=True)
        if liked is not None and _click(liked):
            if _click_menu_item(page, T["unlike"], timeout=5):
                did.append("unliked")
                _human_pause(0.9, 1.4)
            else:
                page.keyboard.press("Escape")

        if not did:
            return False, "no Unfollow/Unlike entry found"

        _human_pause(1.0, 1.6)
        # Verify: neither "Following" nor "Liked" may remain. On a retry a fully
        # unfollowed page shows only Follow/Like and returns "already unfollowed".
        for _ in range(6):
            still_following = _find_button(page, T["following"], prefer_popup=True) is not None
            still_liked = _find_button(page, T["liked"], prefer_popup=True) is not None
            if not still_following and not still_liked:
                return True, " + ".join(did)
            time.sleep(0.8)
        return False, f"{' + '.join(did)} but page still shows a follow/like state"

    # -- connectivity / interruption handling ------------------------------

    def _connectivity_ok(self, page) -> bool:
        """
        True only when the automation browser can actually reach Facebook.
        Raises SessionError if the window/tab is gone -- that is not a network
        problem, it means resume-from-disk, not wait-in-place.
        """
        if page.is_closed():
            raise SessionError("Browser window was closed.")
        try:
            if not page.evaluate("() => navigator.onLine"):
                return False
            return bool(page.evaluate(
                "async () => { try {"
                "  const c = new AbortController();"
                "  const t = setTimeout(() => c.abort(), 2500);"
                "  await fetch('https://www.facebook.com/favicon.ico',"
                "    {mode:'no-cors', cache:'no-store', signal:c.signal});"
                "  clearTimeout(t); return true;"
                "} catch (e) { return false; } }"
            ))
        except SessionError:
            raise
        except Exception as e:
            msg = str(e).lower()
            if "closed" in msg or "crash" in msg or "target" in msg:
                raise SessionError(f"Browser gone: {e}")
            return False           # evaluate failed for a network reason -> offline

    def _wait_for_connection(self, page, mode: str = "purge", label: str = "") -> bool:
        """
        Block until the internet is back, reacting to Stop within ~1s. Returns
        False if the user cancelled; raises SessionError if the browser died so
        the caller can persist the queue and let the user resume later.
        Only the FIRST drop is logged, so a long outage does not flood the log.
        """
        if self._connectivity_ok(page):
            return True

        msg = f"Paused - waiting for internet{(' (' + label + ')') if label else ''}..."
        announced = False
        while True:
            if mode == "purge" and self.should_stop_purge:
                return False
            if mode == "scan" and self.should_stop_scan:
                return False
            if not announced:
                announced = True
                # Only touch the state that belongs to the running operation, so a
                # scan-time outage never leaks into the purge log or modal.
                if mode == "purge":
                    with self._lock:
                        self.purge_progress["paused"] = True
                        self.purge_progress["current_action"] = msg
                    self._log_event("warning", "Internet interrupted - paused. Auto-resumes when it's back.")
                else:
                    with self._lock:
                        self.scan_info["message"] = msg
                    logger.warning("Scan paused - internet interrupted; auto-resumes when it's back.")
            self._sleep_interruptible(3.0, mode)
            try:
                back = self._connectivity_ok(page)
            except SessionError:
                raise
            if back:
                if mode == "purge":
                    with self._lock:
                        self.purge_progress["paused"] = False
                    self._log_event("info", "Internet restored - resuming.")
                else:
                    logger.info("Internet restored - scan resuming.")
                # A dropped connection often leaves a half-loaded page; give FB a
                # moment before the caller retries navigation.
                time.sleep(1.0)
                return True

    # -- resumable purge queue (crash / power-loss safe) -------------------

    def _write_queue_state(self, items: List[Dict[str, Any]], start_time: str):
        """Atomically checkpoint the queue after every item so power loss is safe."""
        payload = {
            "start_time": start_time,
            "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "items": items,
        }
        tmp = PURGE_QUEUE_FILE.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            os.replace(tmp, PURGE_QUEUE_FILE)
            self._resumable_pending = sum(1 for i in items if i.get("status") == "pending")
        except Exception as e:
            logger.warning(f"Could not checkpoint purge queue: {e}")

    def _clear_queue_state(self):
        try:
            if PURGE_QUEUE_FILE.exists():
                PURGE_QUEUE_FILE.unlink()
        except Exception as e:
            logger.debug(f"Could not clear purge queue file: {e}")
        self._resumable_pending = 0
        with self._lock:
            self.purge_progress["resumable"] = False

    def load_pending_queue(self) -> List[Dict[str, Any]]:
        """Returns the parked queue's items (with per-item status), or []."""
        if not PURGE_QUEUE_FILE.exists():
            return []
        try:
            with open(PURGE_QUEUE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = data.get("items") if isinstance(data, dict) else None
            return items if isinstance(items, list) else []
        except Exception as e:
            logger.warning(f"Could not read parked purge queue: {e}")
            return []

    @property
    def resumable_count(self) -> int:
        if self.is_purging:
            return 0
        return self._resumable_pending

    @property
    def has_resumable_purge(self) -> bool:
        return self.resumable_count > 0

    # -- purge -------------------------------------------------------------

    def stop_purge(self):
        with self._lock:
            if self.is_purging:
                self.should_stop_purge = True
                self.purge_progress["current_action"] = "Stopping after the current item..."
        logger.info("Stop-purge signal received.")

    def discard_queue(self) -> Dict[str, Any]:
        """Throw away a parked removal queue. Removes NOTHING from Facebook -- it
        only cancels the pending job so the app returns to normal."""
        if self.is_purging:
            return {"success": False, "message": "Stop the running purge first."}
        n = self._resumable_pending
        self._clear_queue_state()
        logger.info(f"Discarded parked purge queue ({n} item(s)).")
        return {"success": True, "message": f"Cleared {n} queued removal(s).", "count": n}

    def execute_purge_queue(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Start a fresh removal run. Each item is checkpointed so it survives a
        crash, a closed browser, or a power cut and can be resumed later."""
        with self._lock:
            if self.is_purging:
                return {"success": False, "message": "A purge is already running."}
            if self.is_scanning:
                return {"success": False, "message": "Cannot purge while a scan is running."}

        # Normalize into checkpointable rows carrying their own status.
        queue: List[Dict[str, Any]] = []
        for it in items:
            queue.append({
                "id": it.get("id") or it.get("url"),
                "name": it.get("name", "Unknown"),
                "url": it.get("url", ""),
                "type": (it.get("type") or "friend").lower(),
                "status": "pending",
            })

        with self._lock:
            self.is_purging = True
            self.should_stop_purge = False
            self.purge_progress = self._blank_progress()
            self.purge_progress.update({
                "is_running": True,
                "current_action": "Starting up...",
                "total_items": len(queue),
                "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            })

        self._log_event("info", f"Queued {len(queue)} item(s) for Ultra-Safe removal.")
        return self._purge_worker(queue, time.time(), "purge")

    def resume_purge(self) -> Dict[str, Any]:
        """Pick a parked queue back up and finish the pending items."""
        with self._lock:
            if self.is_purging:
                return {"success": False, "message": "A purge is already running."}
            if self.is_scanning:
                return {"success": False, "message": "Cannot purge while a scan is running."}

        queue = self.load_pending_queue()
        pending = [i for i in queue if i.get("status") == "pending"]
        if not pending:
            self._clear_queue_state()
            return {"success": False, "message": "Nothing left to resume."}

        done = sum(1 for i in queue if i.get("status") == "done")

        # If the last run was killed before its end-of-job save, items already
        # removed on Facebook may still be sitting in the dashboard. Reconcile
        # them out now so the list is honest the moment Resume starts.
        with self._lock:
            for i in queue:
                if i.get("status") == "done" and i.get("url"):
                    self._mark_item_removed(i["url"], i.get("type", "friend"))
            self.save_cached_data()

        with self._lock:
            self.is_purging = True
            self.should_stop_purge = False
            self.purge_progress = self._blank_progress()
            self.purge_progress.update({
                "is_running": True,
                "current_action": f"Resuming - {len(pending)} item(s) left...",
                "total_items": len(queue),
                "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            })

        self._log_event("info", f"Resuming purge: {len(pending)} left, {done} already done.")
        return self._purge_worker(queue, time.time(), "purge-resume")

    def _purge_worker(self, items: List[Dict[str, Any]], start_ts: float, label: str) -> Dict[str, Any]:
        total = len(items)
        handlers = {"friend": self._unfriend, "group": self._leave_group, "page": self._unfollow_page}

        def _recount():
            succ = sum(1 for i in items if i.get("status") == "done")
            fail = sum(1 for i in items if i.get("status") == "failed")
            skip = sum(1 for i in items if i.get("status") == "skipped")
            with self._lock:
                self.purge_progress.update({
                    "successful_items": succ,
                    "failed_items": fail,
                    "skipped_items": skip,
                    "processed_items": succ + fail + skip,
                })

        start_time = self.purge_progress.get("start_time") or time.strftime("%Y-%m-%d %H:%M:%S")
        _recount()
        self._write_queue_state(items, start_time)   # safe from the very first item

        def _job(page, ctx):
            if not self._ensure_authenticated(page, ctx, wait_seconds=180):
                self._log_event("error", "Not signed into Facebook -- purge paused. Log in and Resume.")
                return {"success": False, "message": "Login required.", "paused": True}

            newly_removed: List[Dict[str, str]] = []
            attempts = 0

            def _pause_exit():
                # Persist what we already removed before bailing out, so the
                # dashboard and history are correct even if Resume never happens.
                with self._lock:
                    self.save_cached_data()
                self._append_purge_history(newly_removed)
                return {"success": False, "paused": True}

            for item in items:
                if self.should_stop_purge:
                    self._log_event("warning", "Stopped by you. Remaining items saved -- Resume any time.")
                    break
                if item.get("status") in ("done", "failed", "skipped"):
                    continue

                name = item.get("name", "Unknown")
                itype = (item.get("type") or "friend").lower()
                url = item.get("url", "")
                done_so_far = sum(1 for i in items if i.get("status") in ("done", "failed", "skipped"))

                with self._lock:
                    self.purge_progress.update({
                        "current_item_name": name,
                        "current_item_type": itype,
                        "current_action": f"Removing {itype}: {name} ({done_so_far + 1}/{total})",
                        "elapsed_seconds": int(time.time() - start_ts),
                    })

                if self.is_protected_owner(name, url):
                    item["status"] = "skipped"
                    self._write_queue_state(items, start_time); _recount()
                    self._log_event("warning", f"Skipped your own account: {name}")
                    continue

                handler = handlers.get(itype)
                if handler is None:
                    item["status"] = "skipped"
                    self._write_queue_state(items, start_time); _recount()
                    self._log_event("warning", f"Skipped {name}: unknown type '{itype}'")
                    continue

                # Wait out any outage BEFORE we navigate, so we never burn an item.
                try:
                    if not self._wait_for_connection(page, "purge"):
                        break
                except SessionError:
                    self._log_event("warning", "Browser closed -- purge paused. Reopen it and Resume.")
                    return _pause_exit()

                ok, detail, retries, logical_retries = False, "", 0, 0
                while True:
                    try:
                        ok, detail = handler(page, item)
                        # One clean re-attempt for a genuine miss: the handler
                        # re-navigates and re-checks state every call, so a retry
                        # is safe and rescues items that only failed because the
                        # profile rendered slowly the first time.
                        if ok or logical_retries >= 1 or self.should_stop_purge:
                            break
                        logical_retries += 1
                        self._log_event("info", f"Re-checking {name} once (first pass: {detail}).")
                        _human_pause(1.4, 2.2)
                        continue
                    except TransientError as te:
                        retries += 1
                        if retries > 4:
                            ok, detail = False, f"gave up after {retries - 1} network retries ({te})"
                            break
                        self._log_event("warning", f"Connection hiccup on {name} -- retry {retries}/4.")
                        try:
                            if not self._wait_for_connection(page, "purge", label=name):
                                break
                        except SessionError:
                            self._log_event("warning", "Browser closed -- purge paused. Reopen it and Resume.")
                            return _pause_exit()
                    except SessionError:
                        self._log_event("warning", "Browser closed -- purge paused. Reopen it and Resume.")
                        return _pause_exit()
                    except BlockedError as be:
                        # Do NOT keep hammering -- that deepens the block. Stop now,
                        # leave this item pending, and tell the user to clear it.
                        self._log_event("error",
                            f"⛔ {be}: stopped to protect your account. "
                            "Clear the check in the browser window, then click Resume.")
                        with self._lock:
                            self.purge_progress["blocked"] = True
                        return _pause_exit()
                    except Exception as e:
                        ok, detail = False, f"{type(e).__name__}: {e}"
                        try:
                            page.keyboard.press("Escape")
                        except Exception:
                            pass
                        break

                # User hit Stop mid-item: leave it pending so Resume redoes it cleanly.
                if self.should_stop_purge and not ok:
                    break

                attempts += 1
                if ok:
                    item["status"] = "done"
                    self._log_event("success", f"{itype.capitalize()} removed - {name} ({detail})")
                    self._mark_item_removed(url, itype)
                    newly_removed.append({"name": name, "url": url, "type": itype,
                                          "time": time.strftime("%Y-%m-%d %H:%M:%S")})
                else:
                    item["status"] = "failed"
                    self._log_event("error", f"Could not remove {itype} {name} - {detail}")

                self._write_queue_state(items, start_time); _recount()
                with self._lock:
                    self.purge_progress["elapsed_seconds"] = int(time.time() - start_ts)

                # Anti-ban pacing, only while pending work remains.
                if any(i.get("status") == "pending" for i in items) and not self.should_stop_purge:
                    if attempts % 15 == 0:
                        cool = random.uniform(18.0, 28.0)
                        self._log_event("info", f"Anti-ban cooling break: {cool:.0f}s")
                        self._sleep_interruptible(cool, "purge")
                    else:
                        pause = random.uniform(5.0, 9.0)
                        with self._lock:
                            self.purge_progress["current_action"] = f"Stealth cooldown {pause:.1f}s..."
                        self._sleep_interruptible(pause, "purge")

            with self._lock:
                self.save_cached_data()
            self._append_purge_history(newly_removed)
            return {"success": True, "removed": len(newly_removed)}

        try:
            result = session.submit(_job, label, timeout=None)
        except Exception as e:
            self.last_error = str(e)
            self._log_event("error", f"Purge interrupted: {e} -- remaining items saved for Resume.")
            result = {"success": False, "message": str(e), "paused": True}
        finally:
            pending_left = sum(1 for i in items if i.get("status") == "pending")
            # A user-initiated Stop means "I'm done" -- clear the queue like it
            # always did. Only a genuine interruption (crash, closed browser,
            # network) parks the remainder for Resume.
            park = pending_left > 0 and not self.should_stop_purge
            with self._lock:
                self.is_purging = False
                self.purge_progress["is_running"] = False
                self.purge_progress["finished"] = True
                self.purge_progress["paused"] = False
                self.purge_progress["elapsed_seconds"] = int(time.time() - start_ts)
                self.purge_progress["resumable"] = park
            if park:
                self._write_queue_state(items, start_time)
                with self._lock:
                    if self.purge_progress.get("blocked"):
                        self.purge_progress["current_action"] = (
                            f"⛔ Facebook security check - {pending_left} item(s) left. "
                            "Clear it in the browser, then Resume."
                        )
                    else:
                        self.purge_progress["current_action"] = (
                            f"Paused - {pending_left} item(s) left. Click Resume to finish."
                        )
            else:
                self._clear_queue_state()
                with self._lock:
                    self.purge_progress["current_action"] = (
                        "Purge stopped." if self.should_stop_purge else "Purge complete."
                    )
        return result

    def _sleep_interruptible(self, seconds: float, mode: str):
        """Cooling breaks must react to Stop within ~200ms, not 28 seconds later."""
        end = time.time() + seconds
        while time.time() < end:
            if mode == "purge" and self.should_stop_purge:
                return
            if mode == "scan" and self.should_stop_scan:
                return
            time.sleep(0.2)

    def _mark_item_removed(self, url: str, item_type: str):
        key = PLURAL.get(item_type, "friends")
        target = (url or "").lower().rstrip("/")
        with self._lock:
            self.data[key] = [x for x in self.data.get(key, [])
                              if (x.get("url") or "").lower().rstrip("/") != target]

    def _append_purge_history(self, removed: List[Dict[str, str]]):
        if not removed:
            return
        try:
            history = []
            if PURGE_LOG_FILE.exists():
                with open(PURGE_LOG_FILE, "r", encoding="utf-8") as f:
                    history = json.load(f)
                if not isinstance(history, list):
                    history = []
            history.extend(removed)
            tmp = PURGE_LOG_FILE.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(history[-5000:], f, indent=2, ensure_ascii=False)
            os.replace(tmp, PURGE_LOG_FILE)
        except Exception as e:
            logger.warning(f"Could not append purge history: {e}")


fb_engine = FacebookEngine()


# Backwards-compatible module-level helper (older callers imported this name).
def is_protected_owner(name: str, url: str = "") -> bool:
    return fb_engine.is_protected_owner(name, url)
