import os
from pathlib import Path
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = Path(r"C:\Users\chkam\.gemini\antigravity-ide\brain\06ea7764-1746-441d-a156-618cbe6910ad")
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

def capture():
    with sync_playwright() as p:
        # Use installed Microsoft Edge
        browser = p.chromium.launch(channel="msedge", headless=True)
        
        # 1. Capture Dashboard UI
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto("http://127.0.0.1:8766", wait_until="networkidle", timeout=15000)
        dash_path = ARTIFACT_DIR / "facebook_zenith_dashboard.png"
        page.screenshot(path=str(dash_path), full_page=True)
        print(f"Captured Dashboard to: {dash_path}")

        browser.close()

if __name__ == "__main__":
    capture()
