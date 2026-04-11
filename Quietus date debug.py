#!/usr/bin/env python3
"""
Quietus date debug - renders one article page and prints everything
date-related so we can see exactly what markup is available.
"""

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import re
import time
import json

# Use a known recent article
TEST_URL = "https://thequietus.com/quietus-reviews/album-of-the-week/maria-bc-marathon-review/"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-GB",
        )
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)
        page = context.new_page()
        print(f"Fetching {TEST_URL} ...")
        page.goto(TEST_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)
        html = page.content()
        browser.close()

    # Save full HTML
    with open("debug_quietus_article.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Saved: debug_quietus_article.html")

    soup = BeautifulSoup(html, "html.parser")

    # 1. Meta tags
    print("\n--- Meta tags with 'date' or 'publish' ---")
    for meta in soup.find_all("meta"):
        name = meta.get("name", "") + meta.get("property", "")
        content = meta.get("content", "")
        if any(k in name.lower() for k in ["date", "publish", "time"]):
            print(f"  {name} = {content}")

    # 2. All <time> tags
    print("\n--- All <time> tags ---")
    for t in soup.find_all("time"):
        print(f"  datetime={t.get('datetime')} text={t.get_text(strip=True)[:60]}")

    # 3. JSON-LD
    print("\n--- JSON-LD ---")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            print(f"  {json.dumps(data, indent=2)[:500]}")
        except Exception as e:
            print(f"  parse error: {e}")

    # 4. Any element whose text contains "Published" or a year
    print("\n--- Elements containing 'Published' ---")
    for el in soup.find_all(string=re.compile(r"Published", re.I)):
        print(f"  tag={el.parent.name} text={el.strip()[:100]}")

    # 5. Raw text scan for year patterns
    print("\n--- Page text around years ---")
    text = soup.get_text(" ")
    for m in re.finditer(r".{0,40}202[456789].{0,40}", text):
        snippet = m.group().strip()
        if any(month in snippet for month in ["January","February","March","April","May","June",
                                               "July","August","September","October","November","December"]):
            print(f"  {snippet}")


if __name__ == "__main__":
    main()
