#!/usr/bin/env python3
"""
FT Fiction Page – Debug Script
--------------------------------
Renders https://www.ft.com/fiction with Playwright and dumps
the HTML and any JSON data to files for inspection.

Usage:
    pip install playwright beautifulsoup4
    playwright install chromium
    python ft_debug.py
"""

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json
import time

FEED_URL = "https://www.ft.com/fiction"


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
        """)

        print(f"Fetching {FEED_URL} ...")
        page.goto(FEED_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")

        # Save full HTML
        with open("debug_ft_page.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("Full HTML saved to: debug_ft_page.html")

        # Look for any JSON data blobs
        for script in soup.find_all("script"):
            text = script.string or ""
            if any(x in text for x in ["__NEXT_DATA__", "__INITIAL_STATE__", "window.__data"]):
                try:
                    import re
                    match = re.search(r'=\s*(\{.*\})', text, re.DOTALL)
                    if match:
                        data = json.loads(match.group(1))
                        with open("debug_ft_data.json", "w") as f:
                            json.dump(data, f, indent=2)
                        print("JSON data saved to: debug_ft_data.json")
                except Exception as e:
                    print(f"JSON parse error: {e}")

        # Print all links that look like articles
        print("\n--- Sample article links found ---")
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href not in seen and "/content/" in href:
                print(href)
                seen.add(href)
                if len(seen) >= 20:
                    break

        browser.close()


if __name__ == "__main__":
    main()
