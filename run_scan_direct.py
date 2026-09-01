"""
Standalone Direct Visible Scanner for Facebook Zenith Cleaner
Opens a 100% visible Chromium/Edge browser window, waits for login if needed, and autonomously scans all items.
"""

from pathlib import Path
import random
import time
import unicodedata
import os
import tempfile
import json
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent
SESSION_DIR = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "FBCleanerSession"
SESSION_DIR.mkdir(parents=True, exist_ok=True)
CACHE_FILE = BASE_DIR / "scanned_data.json"

# Never touch your own account: add your name / profile-handle stems here.
PROTECTED_STEMS = {"your_name", "your_username"}

def normalize_text(text: str) -> str:
    if not text:
        return ""
    nfd_str = unicodedata.normalize("NFD", str(text))
    stripped = "".join(c for c in nfd_str if unicodedata.category(c) != "Mn")
    return stripped.lower().strip()

def is_protected_owner(name: str, url: str = "") -> bool:
    name_norm = normalize_text(name)
    url_norm = normalize_text(url)
    for stem in PROTECTED_STEMS:
        if stem in name_norm or stem in url_norm:
            return True
    return False

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
            "--no-sandbox"
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

            for _ in range(90):
                time.sleep(2)
                if "facebook.com" in page.url and page.locator('input[name="email"], button[name="login"]').count() == 0 and "login" not in page.url.lower():
                    print("[OK] Logged in successfully!")
                    break

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
                    const href = (link.href || '').split('?')[0].split('&')[0];
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

            for it in discovered:
                if not is_protected_owner(it["name"], it["url"]):
                    if it["name"] not in friends_map:
                        friends_map[it["name"]] = it

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

            for it in discovered:
                if not is_protected_owner(it["name"], it["url"]):
                    if it["name"] not in groups_map:
                        groups_map[it["name"]] = it

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

            for it in discovered:
                if not is_protected_owner(it["name"], it["url"]):
                    if it["name"] not in pages_map:
                        pages_map[it["name"]] = it

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
