# Facebook Zenith Cleaner

Desktop app for triaging and bulk-removing Facebook **friends**, **joined groups**, and **liked/followed pages**.

Scans your account into a local dashboard, lets you review every item and uncheck the ones you want to keep, then removes the rest at a human pace with anti-block cooling breaks.

---

## Quick start

```bash
setup.bat
```

Run once. It installs the Python packages, downloads the bundled Chromium, builds the icon, and puts the shortcut on your desktop.

Then launch from **Facebook Zenith Cleaner** on the desktop (or run `launch.vbs`). The dashboard opens at `http://127.0.0.1:8766`.

1. **Open Browser** → log into Facebook once. The session is remembered.
2. **Scan All** (or **Scan Friends/Groups/Pages Only**).
3. Review the list. Everything starts checked — **uncheck what you want to keep**.
4. **Execute Ultra-Safe Purge**.

---

## How it works

One visible Chromium window, driven by Playwright, owned by a single worker thread. You log in there yourself; the app never sees or stores your password. The profile lives in `%LOCALAPPDATA%\FBCleaner\Profile` — deliberately outside OneDrive, because sync locks corrupt Chromium profiles.

| Category | Source |
|---|---|
| Friends | `/me/friends` |
| Groups | `/groups/joins` |
| Pages | `/pages/?category=liked` **and** `/pages/?category=following` |

Scanning is event-driven: each scroll returns the moment new content actually renders instead of sleeping a fixed interval, and a list ends after three consecutive quiet passes (count *and* page height both stopped moving). That makes large lists 2–3× faster to scan without truncating results. Names are Unicode-normalized, so stylized and Urdu names are handled correctly. Your own account is identified by the `c_user` cookie and can never be queued for removal.

**Removal pacing:** 5–9s between items, plus an 18–28s cooling break every 15. Each removal is verified against the page afterwards ("Add friend" reappeared, "Join group" reappeared), so the success count reflects what actually happened rather than what was clicked. Items already removed are detected and skipped instead of counted as failures.

**Interruption-proof.** Every removal is checkpointed to `purge_queue.json` as it happens, so nothing is ever lost:

- **Internet drops mid-run** → the purge *pauses* (it never counts a network blip as a failed removal), waits for the connection to come back, then retries the exact item it was on and carries on. The modal shows "⏸️ Paused — waiting for the internet".
- **Browser closed, app killed, or power cut** → the parked queue survives on disk. On the next launch the dashboard shows a **Resume Purge** banner with the exact count still to go; one click continues from precisely where it left off, skipping everything already done.
- **Facebook throws a security checkpoint / "temporarily blocked" wall** → the purge stops *immediately* instead of hammering the block (which would only deepen it), parks the rest, and tells you to clear the check in the browser and then Resume. This protects the account.
- Stopping manually also parks the remainder, so you can Resume later.

Every removal is **verified against the page** before it counts — unfriend needs "Add friend" back, leave needs "Join" back, unfollow needs the follow/like state cleared. Anything that can't be confirmed is retried once (each attempt re-navigates and re-checks, so it's safe) and otherwise reported as a failure rather than a false success.

Stop is available at any time and takes effect within about a second, including during a cooling break or a pause.

---

## Dashboard

- **Per-category control** — each of the Friends, Groups, and Pages cards has its own **Scan** and **Delete Checked** button, so you scan and remove one category at a time without touching the others. The Delete button shows the exact checked count and disables itself when nothing is selected. (Scan All and Purge-everything remain for when you do want the lot.)
- **Tabs** per category, plus a Markdown checklist view
- **Search** by name or link
- **Pagination** at 50 / 100 / 300 / All per page
- **Batch controls**: select or keep a page, invert a page, select or keep a whole tab
- **Purge scope**: current tab only, or everything checked across all tabs
- **Export** to CSV (UTF-8 BOM, so Excel renders Urdu correctly) or Markdown
- **Import** JSON from the in-tab collector script, by paste, file picker, or drag-and-drop

Unchecking survives a rescan — a rescan will not silently re-check items you decided to keep. Cancelling a scan mid-run keeps the list you already had instead of replacing it with the partial result.

---

## Files

```
backend/fb_engine.py   browser session, scanners, removal flows
backend/app.py         FastAPI server + JSON API
frontend/              dashboard (index.html, app.js, style.css)
launch.vbs             desktop launcher (starts the server, opens the dashboard)
setup.bat              one-time install
run_fb_cleaner.bat     same thing with a visible console, for debugging
create_icon.py         regenerates fb_cleaner.ico
create_desktop_shortcut.py  rewrites the desktop shortcut and refreshes the icon cache
scanned_data.json      your scanned lists and keep/remove choices
purge_history.json     what was removed and when
fb_cleaner.log         run log — check here first when something misbehaves
```

To change the icon: edit `create_icon.py`, then run `python create_icon.py && python create_desktop_shortcut.py`.

---

## Troubleshooting

**"Could not open the automation browser"** — a previous browser is still holding the profile. The app force-clears these on its own; if it persists, close every Chromium window titled *Facebook* and retry.

**Scan finds 0 items** — you are signed out. Click **Open Browser** and check the badge reads *Signed in*.

**Nothing happens on double-click** — run `run_fb_cleaner.bat` to see the console, or read `fb_cleaner_console.log`.

**Removals failing** — Facebook may be rate-limiting. Stop, wait an hour, resume. The log names the exact step that failed for each item.

---

## Notes

- Removals are permanent. Facebook has no undo for unfriending, leaving a group, or unliking a page.
- Purge only ever acts on items still checked **on the server**, resolved at start time — a stale browser tab cannot remove the wrong people.
- Requires Python 3.11+ on Windows.
