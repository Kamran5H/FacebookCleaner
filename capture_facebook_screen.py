import os
from pathlib import Path
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = Path(r"C:\Users\chkam\.gemini\antigravity-ide\brain\06ea7764-1746-441d-a156-618cbe6910ad")

def capture_fb():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto("https://www.facebook.com", wait_until="domcontentloaded", timeout=20000)
        fb_path = ARTIFACT_DIR / "facebook_login_view.png"
        page.screenshot(path=str(fb_path))
        print(f"Captured Facebook view to: {fb_path}")
        browser.close()

if __name__ == "__main__":
    capture_fb()
