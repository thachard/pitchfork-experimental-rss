#!/usr/bin/env python3
"""
Pitchfork Debug Script
-----------------------
Renders the Pitchfork experimental reviews page with Playwright
and dumps the raw HTML and __NEXT_DATA__ JSON to files so we
can inspect the real page structure.

Usage:
    pip install playwright beautifulsoup4
    playwright install chromium
    python pitchfork_debug.py
"""

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json
import time

BASE_URL = "https://pitchfork.com"
FEED_URL = f"{BASE_URL}/genre/experimental/review/"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            timezone_id="America/New_York",
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

        page = context.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        """)

        print(f"Fetching {FEED_URL} ...")
        page.goto(FEED_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")

        # Dump full HTML for inspection
        with open("debug_page.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("Full HTML saved to: debug_page.html")

        # Dump __NEXT_DATA__ JSON if present
        next_data_tag = soup.find("script", id="__NEXT_DATA__")
        if next_data_tag:
            try:
                data = json.loads(next_data_tag.string)
                with open("debug_next_data.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                print("__NEXT_DATA__ JSON saved to: debug_next_data.json")
            except json.JSONDecodeError as e:
                print(f"Could not parse __NEXT_DATA__: {e}")
        else:
            print("No __NEXT_DATA__ tag found on page.")

        # Print all unique <a> hrefs that contain "pitchfork.com" or start with "/"
        print("\n--- Sample links found on page ---")
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href not in seen and ("review" in href or "album" in href):
                print(href)
                seen.add(href)
                if len(seen) >= 30:
                    break

        browser.close()


if __name__ == "__main__":
    main()
