#!/usr/bin/env python3
"""
WSJ Author Page – Debug Script
--------------------------------
Renders https://www.wsj.com/news/author/sam-sacks with Playwright
and dumps the HTML for inspection.

Usage:
    pip install playwright beautifulsoup4
    playwright install chromium
    python wsj_debug.py
"""

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json
import time

FEED_URL = "https://www.wsj.com/news/author/sam-sacks"


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

        # Save full HTML
        with open("debug_wsj_page.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("Full HTML saved to: debug_wsj_page.html")

        # Save any __NEXT_DATA__ JSON
        next_data = soup.find("script", id="__NEXT_DATA__")
        if next_data:
            try:
                data = json.loads(next_data.string)
                with open("debug_wsj_data.json", "w") as f:
                    json.dump(data, f, indent=2)
                print("__NEXT_DATA__ saved to: debug_wsj_data.json")
            except Exception as e:
                print(f"JSON parse error: {e}")
        else:
            print("No __NEXT_DATA__ found.")

        # Print article-like links
        print("\n--- Sample links found ---")
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href not in seen and "/articles/" in href:
                print(href)
                seen.add(href)
                if len(seen) >= 20:
                    break

        # Print time tags
        print("\n--- Time tags ---")
        for t in soup.find_all("time")[:10]:
            print(f"  datetime={t.get('datetime')} text={t.get_text(strip=True)[:50]}")

        browser.close()


if __name__ == "__main__":
    main()
