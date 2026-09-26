"""
Standalone Direct Visible Scanner for Facebook Zenith Cleaner
Opens a 100% visible Chromium/Edge browser window, waits for login if needed, and autonomously scans all items.
"""

from pathlib import Path
import random
import time
import os
import tempfile
import json
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent
SESSION_DIR = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "FBCleanerSession"
SESSION_DIR.mkdir(parents=True, exist_ok=True)
# Same location the dashboard reads (FBC_DATA_DIR overrides it, as in the app).
CACHE_FILE = Path(os.environ.get("FBC_DATA_DIR") or BASE_DIR) / "scanned_data.json"


def url_key(url: str) -> str:
    """Stable identity for an item: two friends can share a name, never a URL."""
    return (url or "").strip().lower().rstrip("/")


def owner_id_from_cookies(context) -> str:
    """The signed-in account's numeric id (Facebook's c_user cookie)."""
    for c in context.cookies("https://www.facebook.com"):
        if c.get("name") == "c_user":
            return str(c.get("value") or "")
    return ""


def is_protected_owner(url: str, owner_id: str) -> bool:
    """True only for the signed-in account itself -- never a name match, which
    would silently hide every friend who shares the owner's name."""
    u = url_key(url)
    return bool(owner_id) and (f"id={owner_id}" in u or u.endswith(f"/{owner_id}"))


def load_previous_choices() -> dict:
    """url -> selected, so a re-scan never forgets which items you chose to KEEP."""
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            old = json.load(f)
    except (OSError, ValueError):
        return {}
    choices = {}
    for key in ("friends", "groups", "pages"):
        for it in old.get(key, []) if isinstance(old, dict) else []:
            if isinstance(it, dict) and it.get("url"):
                choices[url_key(it["url"])] = bool(it.get("selected", True))
    return choices


def collect(found: dict, discovered: list, owner_id: str) -> None:
    for it in discovered:
        key = url_key(it.get("url", ""))
        if key and key not in found and not is_protected_owner(key, owner_id):
            found[key] = it

def scan_headful_direct():
    print("=" * 60)
    print("[START] LAUNCHING 100% VISIBLE FACEBOOK SCANNER")
    print("=" * 60)

    with sync_playwright() as p:
        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-notifications",
            "--start-maximized",
            "--no-default-browser-check",
        ]

        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(SESSION_DIR),
                headless=False,
                args=args,
                viewport=None,
                locale="en-US"
            )
        except Exception:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(SESSION_DIR),
                channel="chrome",
                headless=False,
                args=args,
                viewport=None,
                locale="en-US"
            )

        page = context.pages[0] if context.pages else context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")

        # 1. Navigate to Facebook Friends
        print("\nNavigating to Facebook (/me/friends)...")
        page.goto("https://www.facebook.com/me/friends", timeout=60000, wait_until="domcontentloaded")
        time.sleep(3)

        # Check if logged in
        if "login" in page.url.lower() or page.locator('input[name="email"], button[name="login"]').count() > 0:
            print("\n" + "!" * 60)
            print("[ACTION REQUIRED] Please log into your Facebook account in the opened browser window.")
            print("Waiting for you to log in...")
            print("!" * 60)

            for _ in range(150):
                time.sleep(2)
                if "facebook.com" in page.url and page.locator('input[name="email"], button[name="login"]').count() == 0 and "login" not in page.url.lower():
                    print("[OK] Logged in successfully!")
                    break
            else:
                # Scanning a login page would save empty lists over your real data.
                print("[ABORT] Not logged in after 5 minutes - nothing was changed.")
                context.close()
                return

        owner_id = owner_id_from_cookies(context)
        previous = load_previous_choices()

        time.sleep(2)

        # 2. Scan Friends
        print("\n" + "-" * 50)
        print("[STEP 1/3] Scanning Friends (/me/friends)...")
        if "friends" not in page.url.lower():
            page.goto("https://www.facebook.com/me/friends", timeout=60000, wait_until="domcontentloaded")
            time.sleep(3)

        friends_map = {}
        no_new = 0
        last_count = 0

        for s in range(50):
            discovered = page.evaluate("""() => {
                const results = [];
                const mainArea = document.querySelector('div[role="main"]') || document.body;
                const cards = Array.from(mainArea.querySelectorAll('div[role="listitem"], div[role="gridcell"], div[class*="x1yztbdb"]'));
                for (const card of cards) {
                    const link = card.querySelector('a[role="link"], a[href*="facebook.com/"], a[href^="/"]');
                    if (!link) continue;
                    // Keep ?id= for numeric profiles: stripping it would turn every
                    // profile.php friend into the same (useless) URL.
                    let href = '';
                    try {
                        const u = new URL(link.href);
                        const pid = u.pathname === '/profile.php' ? u.searchParams.get('id') : '';
                        href = pid ? `${u.origin}/profile.php?id=${pid}` : u.origin + u.pathname;
                    } catch (e) { continue; }
                    if (!href || href.includes('/messages') || href.includes('/notifications') || href.includes('/saved')) continue;
                    const rawText = (card.innerText || link.innerText || '').trim();
                    if (!rawText) continue;
                    const cardLower = rawText.toLowerCase();
                    if (cardLower.includes('add friend') || cardLower.includes('دوست شامل کریں') || cardLower.includes('friend request') || cardLower.includes('people you may know')) continue;
                    const name = rawText.split('\\n')[0].trim();
                    if (!name || name.length < 2 || name.length > 90) continue;
                    let avatar = '';
                    const img = card.querySelector('img') || link.querySelector('img');
                    if (img && img.src && !img.src.includes('data:image/svg')) avatar = img.src;
                    results.push({ id: href, name: name, url: href, avatar: avatar, type: 'friend', selected: true });
                }
                return results;
            }""")

            collect(friends_map, discovered, owner_id)

            c = len(friends_map)
            print(f" -> Discovered {c} friends (scroll {s + 1})")
            if c >= 500:
                break
            if c == last_count:
                no_new += 1
                if no_new >= 6:
                    break
            else:
                no_new = 0
                last_count = c
            page.mouse.wheel(0, random.randint(800, 1200))
            time.sleep(random.uniform(1.0, 1.6))

        # 3. Scan Groups
        print("\n" + "-" * 50)
        print("[STEP 2/3] Scanning Groups (/groups/joins)...")
        page.goto("https://www.facebook.com/groups/joins", timeout=60000, wait_until="domcontentloaded")
        time.sleep(3)

        groups_map = {}
        no_new = 0
        last_count = 0

        for s in range(30):
            discovered = page.evaluate("""() => {
                const links = Array.from(document.querySelectorAll('a[href*="/groups/"]'));
                const results = [];
                for (const l of links) {
                    const href = (l.href || '').split('?')[0].split('&')[0];
                    if (!href || href.endsWith('/groups/') || href.endsWith('/joins') || href.includes('/feed/')) continue;
                    const text = (l.innerText || '').trim().split('\\n')[0].trim();
                    if (!text || text.length < 2 || ['groups', 'feed', 'discover', 'your groups', 'create group'].includes(text.toLowerCase())) continue;
                    let avatar = '';
                    const img = l.querySelector('img') || (l.parentElement ? l.parentElement.querySelector('img') : null);
                    if (img && img.src && !img.src.includes('data:image/svg')) avatar = img.src;
                    results.push({ id: href, name: text, url: href, avatar: avatar, type: 'group', selected: true });
                }
                return results;
            }""")

            collect(groups_map, discovered, owner_id)

            c = len(groups_map)
            print(f" -> Discovered {c} groups (scroll {s + 1})")
            if c == last_count:
                no_new += 1
                if no_new >= 5:
                    break
            else:
                no_new = 0
                last_count = c
            page.mouse.wheel(0, random.randint(600, 1000))
            time.sleep(random.uniform(1.0, 1.5))

        # 4. Scan Pages
        print("\n" + "-" * 50)
        print("[STEP 3/3] Scanning Pages (/pages/?category=liked)...")
        page.goto("https://www.facebook.com/pages/?category=liked", timeout=60000, wait_until="domcontentloaded")
        time.sleep(3)

        pages_map = {}
        no_new = 0
        last_count = 0

        for s in range(30):
            discovered = page.evaluate("""() => {
                const links = Array.from(document.querySelectorAll('a[role="link"][href*="facebook.com/"], a[href^="/"]'));
                const results = [];
                for (const l of links) {
                    const href = (l.href || '').split('?')[0].split('&')[0];
                    if (!href || href.includes('category=') || href.includes('/pages') || href.includes('/friends') || href.includes('/groups')) continue;
                    const text = (l.innerText || '').trim().split('\\n')[0].trim();
                    if (!text || text.length < 2 || ['pages', 'liked pages', 'invitations'].includes(text.toLowerCase())) continue;
                    let avatar = '';
                    const img = l.querySelector('img') || (l.parentElement ? l.parentElement.querySelector('img') : null);
                    if (img && img.src && !img.src.includes('data:image/svg')) avatar = img.src;
                    results.push({ id: href, name: text, url: href, avatar: avatar, type: 'page', selected: true });
                }
                return results;
            }""")

            collect(pages_map, discovered, owner_id)

            c = len(pages_map)
            print(f" -> Discovered {c} pages (scroll {s + 1})")
            if c == last_count:
                no_new += 1
                if no_new >= 5:
                    break
            else:
                no_new = 0
                last_count = c
            page.mouse.wheel(0, random.randint(600, 1000))
            time.sleep(random.uniform(1.0, 1.5))

        # Keep every KEEP/REMOVE choice from the previous scan.
        for found in (friends_map, groups_map, pages_map):
            for key, it in found.items():
                if key in previous:
                    it["selected"] = previous[key]

        out_data = {
            "friends": list(friends_map.values()),
            "groups": list(groups_map.values()),
            "pages": list(pages_map.values()),
            "last_scan_time": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        # Atomic write
        tmp_file = CACHE_FILE.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(out_data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_file, CACHE_FILE)

        print("\n" + "=" * 60)
        print(f"[SUCCESS] Scanned {len(friends_map)} Friends, {len(groups_map)} Groups, {len(pages_map)} Pages!")
        print(f"Data atomically saved to {CACHE_FILE}")
        print("=" * 60)
        context.close()

if __name__ == "__main__":
    scan_headful_direct()
