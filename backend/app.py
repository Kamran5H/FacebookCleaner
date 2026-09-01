"""
Facebook Zenith Cleaner - FastAPI backend & local web server (v2.0)

Serves the dashboard and exposes the engine over a small JSON API. Long-running
work (scan / purge) is started on a worker thread and observed through
/api/status and /api/purge/progress; the browser itself lives on the engine's
single session thread, so nothing here ever touches Playwright directly.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"
FRONTEND_DIR = BASE_DIR / "frontend"

# pythonw.exe (used by the desktop launcher) hands us sys.stdout/stderr == None.
# Anything that prints then raises AttributeError and the app dies with no window
# and no message. Point both at a console log file instead.
if sys.stdout is None or sys.stderr is None:
    try:
        _console_log = open(BASE_DIR / "fb_cleaner_console.log", "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = _console_log
        if sys.stderr is None:
            sys.stderr = _console_log
    except Exception:
        import io as _io
        sys.stdout = sys.stdout or _io.StringIO()
        sys.stderr = sys.stderr or _io.StringIO()

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fb_engine import (  # noqa: E402
    CATEGORY_URLS,
    PLURAL,
    SINGULAR,
    fb_engine,
    logger,
    session,
)

APP_VERSION = "2.0.0"
DEFAULT_PORT = 8766

app = FastAPI(
    title="Facebook Zenith Cleaner",
    description="Facebook friends, groups and pages triage & Ultra-Safe removal suite",
    version=APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8766", "http://localhost:8766"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _no_store_frontend(request, call_next):
    """Never let the local app window cache the frontend -- always ship the latest
    JS/CSS. This is localhost, so there is no bandwidth cost to skipping the cache."""
    response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path.endswith((".js", ".css")):
        response.headers["Cache-Control"] = "no-store, must-revalidate"
    return response


# --- Models -----------------------------------------------------------------

class PurgeRequest(BaseModel):
    category: Optional[str] = None
    selected_items: Optional[List[Dict[str, Any]]] = None


class ToggleItemRequest(BaseModel):
    item_id: str
    item_type: str
    selected: bool


class BulkToggleRequest(BaseModel):
    item_type: str = "friends"
    item_ids: List[str] = []
    selected: bool = True


class BatchToggleRequest(BaseModel):
    item_type: Optional[str] = "all"
    selected: bool = True


def _category_key(value: str) -> Optional[str]:
    """Accepts 'friend'/'friends' etc. and returns the plural data key."""
    v = (value or "").strip().lower()
    if v in ("friends", "groups", "pages"):
        return v
    if v in PLURAL:
        return PLURAL[v]
    return None


# --- Health & status --------------------------------------------------------

@app.get("/api/health")
def api_health():
    return {"status": "ok", "app": "Facebook Zenith Cleaner", "version": APP_VERSION}


@app.get("/api/status")
def get_status():
    with fb_engine._lock:
        counts = {k: len(fb_engine.data.get(k, [])) for k in ("friends", "groups", "pages")}
        selected = {
            k: sum(1 for i in fb_engine.data.get(k, []) if i.get("selected", True))
            for k in ("friends", "groups", "pages")
        }
        scan_info = dict(fb_engine.scan_info)
        last_scan = fb_engine.data.get("last_scan_time")

    counts["total"] = sum(counts.values())
    selected["total"] = sum(selected.values())

    return {
        "isScanning": fb_engine.is_scanning,
        "isPurging": fb_engine.is_purging,
        "scanInfo": scan_info,
        "lastScanTime": last_scan,
        "counts": counts,
        "selected": selected,
        "purgeProgress": fb_engine.progress_snapshot(),
        "resumablePurge": {
            "available": fb_engine.has_resumable_purge,
            "count": fb_engine.resumable_count,
        },
        "session": {
            "open": session.is_alive,
            "browser": session.browser_kind,
            "queued": session.queue_depth,
        },
        "lastError": fb_engine.last_error or session.last_error,
        "owner": {
            "id": fb_engine.owner_id,
            "url": fb_engine.owner_url,
            "name": fb_engine.owner_name,
        },
    }


# --- Browser session --------------------------------------------------------

@app.post("/api/browser/open")
def open_browser_for_login():
    return fb_engine.open_browser_for_user()


@app.post("/api/browser/close")
def close_browser():
    if fb_engine.is_scanning or fb_engine.is_purging:
        return {"success": False, "message": "Stop the running scan or purge first."}
    session.stop()
    return {"success": True, "message": "Browser session closed."}


@app.get("/api/auth/check")
def check_auth():
    return fb_engine.check_login_status()


# --- Scanning ---------------------------------------------------------------

def _start_background(fn, *args) -> None:
    threading.Thread(target=fn, args=args, daemon=True).start()


@app.post("/api/scan")
def trigger_scan():
    return trigger_category_scan("all")


@app.post("/api/scan/stop")
def stop_scan_endpoint():
    if not fb_engine.is_scanning:
        return {"success": False, "message": "No scan is running."}
    fb_engine.stop_scan()
    return {"success": True, "message": "Stopping the scan..."}


@app.post("/api/scan/{category}")
def trigger_category_scan(category: str):
    if fb_engine.is_scanning:
        return {"success": False, "message": "A scan is already running."}
    if fb_engine.is_purging:
        return {"success": False, "message": "Cannot scan while a purge is running."}

    category = (category or "all").strip().lower()
    if category not in list(CATEGORY_URLS) + ["all"]:
        return {"success": False, "message": f"Invalid category '{category}'."}

    try:
        session.start()
    except Exception as e:
        fb_engine.last_error = str(e)
        return {"success": False, "message": f"Could not start the browser: {e}"}

    if category == "all":
        _start_background(fb_engine.scan_all_full)
    else:
        _start_background(fb_engine.scan_single_category, category)

    return {"success": True, "message": f"Scan started for {category}."}


# --- Data -------------------------------------------------------------------

@app.get("/api/data")
def get_scanned_data():
    with fb_engine._lock:
        return {
            "friends": list(fb_engine.data.get("friends", [])),
            "groups": list(fb_engine.data.get("groups", [])),
            "pages": list(fb_engine.data.get("pages", [])),
            "lastScanTime": fb_engine.data.get("last_scan_time"),
        }


@app.post("/api/data/clear")
def clear_data(payload: Optional[Dict[str, Any]] = None):
    target = (payload or {}).get("category", "all")
    keys = ["friends", "groups", "pages"] if target == "all" else [_category_key(target)]
    keys = [k for k in keys if k]
    if not keys:
        return {"success": False, "message": "Unknown category."}
    with fb_engine._lock:
        for k in keys:
            fb_engine.data[k] = []
        fb_engine.save_cached_data()
    return {"success": True, "cleared": keys}


@app.post("/api/import")
def import_scanned_data(payload: Dict[str, Any]):
    """Imports lists produced by the in-tab collector script."""
    imported = {}
    with fb_engine._lock:
        for key in ("friends", "groups", "pages"):
            incoming = payload.get(key)
            if isinstance(incoming, list) and incoming:
                cleaned = fb_engine._sanitize_items(incoming, SINGULAR[key])
                fb_engine.data[key] = fb_engine._merge_preserving_choices(key, cleaned)
            imported[key] = len(fb_engine.data.get(key, []))
        fb_engine.data["last_scan_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        fb_engine.save_cached_data()
    return {"success": True, "counts": imported}


# --- Selection --------------------------------------------------------------

@app.post("/api/items/toggle")
def toggle_item(req: ToggleItemRequest):
    key = _category_key(req.item_type)
    with fb_engine._lock:
        keys = [key] if key else ["friends", "groups", "pages"]
        for k in keys:
            for item in fb_engine.data.get(k, []):
                if item.get("id") == req.item_id or item.get("url") == req.item_id:
                    item["selected"] = req.selected
                    fb_engine.save_cached_data()
                    return {"success": True, "item": item}
    raise HTTPException(status_code=404, detail="Item not found")


@app.post("/api/items/toggle-bulk")
def toggle_bulk(req: BulkToggleRequest):
    """One request for a whole page of checkboxes instead of 300 separate ones."""
    key = _category_key(req.item_type)
    if not key:
        return {"success": False, "message": f"Unknown type '{req.item_type}'."}
    wanted = {i for i in req.item_ids}
    updated = 0
    with fb_engine._lock:
        for item in fb_engine.data.get(key, []):
            if item.get("id") in wanted or item.get("url") in wanted:
                item["selected"] = req.selected
                updated += 1
        fb_engine.save_cached_data()
    return {"success": True, "updated": updated}


@app.post("/api/items/invert")
def invert_items(req: BulkToggleRequest):
    key = _category_key(req.item_type)
    if not key:
        return {"success": False, "message": f"Unknown type '{req.item_type}'."}
    wanted = {i for i in req.item_ids}
    updated = 0
    with fb_engine._lock:
        for item in fb_engine.data.get(key, []):
            if item.get("id") in wanted or item.get("url") in wanted:
                item["selected"] = not item.get("selected", True)
                updated += 1
        fb_engine.save_cached_data()
    return {"success": True, "updated": updated}


@app.post("/api/items/batch-toggle")
def batch_toggle(req: BatchToggleRequest):
    if req.item_type in ("all", "markdown", None):
        keys = ["friends", "groups", "pages"]
    else:
        key = _category_key(req.item_type)
        if not key:
            return {"success": False, "message": f"Unknown type '{req.item_type}'."}
        keys = [key]

    updated = 0
    with fb_engine._lock:
        for k in keys:
            for item in fb_engine.data.get(k, []):
                item["selected"] = req.selected
                updated += 1
        fb_engine.save_cached_data()
    return {"success": True, "updated": updated}


# --- Purge ------------------------------------------------------------------

@app.post("/api/purge/start")
def start_purge(req: PurgeRequest):
    if fb_engine.is_purging:
        return {"success": False, "message": "A purge is already running."}
    if fb_engine.is_scanning:
        return {"success": False, "message": "Cannot purge while a scan is running."}

    # Always resolve the queue against server-side state: the client sends ids,
    # never the items to act on, so a stale tab cannot remove the wrong people.
    requested_ids: Optional[set] = None
    if req.selected_items:
        requested_ids = {
            (x.get("id") or x.get("url"))
            for x in req.selected_items
            if isinstance(x, dict) and (x.get("id") or x.get("url"))
        }

    if req.category and req.category not in ("all", None):
        key = _category_key(req.category)
        if not key:
            return {"success": False, "message": f"Unknown category '{req.category}'."}
        keys = [key]
    else:
        keys = ["friends", "groups", "pages"]

    queue: List[Dict[str, Any]] = []
    with fb_engine._lock:
        for k in keys:
            for item in fb_engine.data.get(k, []):
                if not item.get("selected", True):
                    continue
                # requested_ids may hold ids OR urls (built as `id or url`), so match
                # on either — the same way the toggle endpoints identify items. Matching
                # id-only would silently skip collector-imported items that only have a url.
                if requested_ids is not None and not (
                    item.get("id") in requested_ids or item.get("url") in requested_ids
                ):
                    continue
                if fb_engine.is_protected_owner(item.get("name", ""), item.get("url", "")):
                    continue
                queue.append(dict(item))

    if not queue:
        where = req.category.capitalize() if req.category and req.category != "all" else "any tab"
        return {"success": False, "message": f"Nothing is checked for removal in {where}."}

    try:
        session.start()
    except Exception as e:
        return {"success": False, "message": f"Could not start the browser: {e}"}

    _start_background(fb_engine.execute_purge_queue, queue)
    return {"success": True, "message": f"Removing {len(queue)} item(s).", "count": len(queue)}


@app.post("/api/purge/stop")
def stop_purge():
    if not fb_engine.is_purging:
        return {"success": False, "message": "No purge is running."}
    fb_engine.stop_purge()
    return {"success": True, "message": "Stopping after the current item..."}


@app.post("/api/purge/discard")
def discard_purge_queue():
    """Cancel a parked (resumable) removal queue. Removes nothing from Facebook."""
    return fb_engine.discard_queue()


@app.post("/api/purge/resume")
def resume_purge():
    """Finish a purge that was interrupted by a crash, power loss, or closed browser."""
    if fb_engine.is_purging:
        return {"success": False, "message": "A purge is already running."}
    if fb_engine.is_scanning:
        return {"success": False, "message": "Cannot purge while a scan is running."}
    if not fb_engine.has_resumable_purge:
        return {"success": False, "message": "Nothing to resume."}

    try:
        session.start()
    except Exception as e:
        return {"success": False, "message": f"Could not start the browser: {e}"}

    count = fb_engine.resumable_count
    _start_background(fb_engine.resume_purge)
    return {"success": True, "message": f"Resuming {count} item(s).", "count": count}


@app.get("/api/purge/progress")
def get_purge_progress():
    return fb_engine.progress_snapshot()


@app.get("/api/purge/history")
def get_purge_history():
    path = BASE_DIR / "purge_history.json"
    if not path.exists():
        return {"history": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {"history": data if isinstance(data, list) else []}
    except Exception as e:
        return {"history": [], "error": str(e)}


# --- Exports ----------------------------------------------------------------

def _all_rows():
    with fb_engine._lock:
        return (
            list(fb_engine.data.get("friends", [])),
            list(fb_engine.data.get("groups", [])),
            list(fb_engine.data.get("pages", [])),
        )


@app.get("/api/export/csv", response_class=PlainTextResponse)
def export_csv_data():
    friends, groups, pages = _all_rows()
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["Type", "Name", "URL", "Status", "Details"])
    for label, rows in (("Friend", friends), ("Group", groups), ("Page", pages)):
        for r in rows:
            writer.writerow([
                label,
                r.get("name", ""),
                r.get("url", ""),
                "REMOVE" if r.get("selected", True) else "KEEP",
                r.get("subText", ""),
            ])
    return Response(
        content="\ufeff" + out.getvalue(),  # BOM so Excel reads Urdu names correctly
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="facebook_triage.csv"'},
    )


@app.get("/api/export/markdown", response_class=PlainTextResponse)
def export_markdown_checklist():
    friends, groups, pages = _all_rows()
    lines = [
        "# Facebook Zenith Cleaner - Triage Checklist",
        f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "> `[x]` = slated for REMOVAL  |  `[ ]` = KEEP",
        "",
    ]
    for title, rows in (
        (f"Friends ({len(friends)})", friends),
        (f"Groups ({len(groups)})", groups),
        (f"Pages ({len(pages)})", pages),
    ):
        lines += ["---", "", f"## {title}", ""]
        for r in rows:
            chk = "x" if r.get("selected", True) else " "
            lines.append(f"- [{chk}] [{r.get('name', 'Unknown')}]({r.get('url', '#')})")
        lines.append("")
    return "\n".join(lines)


# --- Static frontend --------------------------------------------------------

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/favicon.ico")
def favicon():
    ico = BASE_DIR / "fb_cleaner.ico"
    if ico.exists():
        return FileResponse(str(ico), media_type="image/x-icon")
    return Response(status_code=204)


@app.get("/facebook_300_collector.js")
def get_collector_js():
    fp = BASE_DIR / "facebook_300_collector.js"
    if fp.exists():
        return FileResponse(str(fp), media_type="application/javascript")
    return PlainTextResponse("// collector script not found", status_code=404)


@app.get("/", response_class=HTMLResponse)
def index_page():
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>Frontend files are missing.</h1>", status_code=500)
    html = index_file.read_text(encoding="utf-8")
    # Cache-bust JS/CSS by file mtime. Without this, the app window happily serves
    # a stale app.js from its heuristic cache -- new buttons render (index.html is
    # no-store) but their handlers are missing, so they look "dead".
    for asset in ("app.js", "style.css"):
        fp = FRONTEND_DIR / asset
        if fp.exists():
            ver = int(fp.stat().st_mtime)
            html = html.replace(f"/static/{asset}", f"/static/{asset}?v={ver}")
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


# --- Server bootstrap -------------------------------------------------------

def open_in_browser(url: str):
    """Opens the dashboard as a chromeless app window when Chrome/Edge is present."""
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for exe in candidates:
        if os.path.exists(exe):
            try:
                subprocess.Popen([exe, f"--app={url}", "--window-size=1500,980"])
                return
            except Exception:
                continue
    webbrowser.open(url)


def is_port_in_use(port: int = DEFAULT_PORT, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.6)
        return s.connect_ex((host, port)) == 0


def start_server(host: str = "127.0.0.1", port: int = DEFAULT_PORT, open_browser: bool = False):
    url = f"http://{host}:{port}"

    if is_port_in_use(port, host):
        # Already running: surface the existing instance instead of dying silently.
        print(f"[INFO] Already running at {url} - focusing the existing window.")
        if open_browser:
            open_in_browser(url)
        return

    if open_browser:
        def _open():
            for _ in range(40):
                if is_port_in_use(port, host):
                    break
                time.sleep(0.25)
            open_in_browser(url)
        threading.Thread(target=_open, daemon=True).start()

    print("=" * 62)
    print("  FACEBOOK ZENITH CLEANER v" + APP_VERSION)
    print(f"  Dashboard: {url}")
    print("=" * 62)

    uvicorn.run(app, host=host, port=port, log_level="warning", access_log=False)


if __name__ == "__main__":
    wants_browser = "--open" in sys.argv or "--browser" in sys.argv
    port = DEFAULT_PORT
    for i, a in enumerate(sys.argv):
        if a == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
    start_server(port=port, open_browser=wants_browser)
