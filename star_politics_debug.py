#!/usr/bin/env python3
"""
Toronto Star – Provincial & Federal Politics Debug Script
----------------------------------------------------------
Renders both pages with Playwright and dumps HTML for inspection.

Usage:
    pip install playwright beautifulsoup4
    playwright install chromium
    python star_politics_debug.py
"""

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time

URLS = [
    ("provincial", "https://www.thestar.com/politics/provincial/"),
    ("federal",    "https://www.thestar.com/politics/federal/"),
]


def debug_page(page, label, url):
    print(f"\n{'='*60}")
    print(f"Fetching: {url}")
    print(f"{'='*60}")

    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    time.sleep(3)
    html = page.content()
    soup = BeautifulSoup(html, "html.parser")

    # Save full HTML
    fname = f"debug_star_{label}.html"
    with open(fname, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML saved to: {fname}")

    # Count time tags
    time_tags = soup.find_all("time")
    print(f"Time tags found: {len(time_tags)}")
    for t in time_tags[:5]:
        print(f"  datetime={t.get('datetime')} text={t.get_text(strip=True)[:40]}")

    # Count card-body divs (what City Hall used)
    card_bodies = soup.find_all("div", class_="card-body")
    print(f"div.card-body elements: {len(card_bodies)}")

    # Count all article links
    article_links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/article_" in href or ("/politics/" in href and len(href) > 40):
            article_links.add(href)
    print(f"Article-like links found: {len(article_links)}")
    for l in list(article_links)[:5]:
        print(f"  {l[:100]}")

    # Show classes of elements containing both a link and a heading
    print("\nContainers with heading + link:")
    seen = set()
    for h in soup.find_all(["h2", "h3"]):
        a = h.find("a", href=True) or h.find_parent("a", href=True)
        if not a:
            # check parent for a link
            p = h.parent
            a = p.find("a", href=True) if p else None
        if a:
            href = a.get("href", "")
            if href in seen or len(href) < 20:
                continue
            seen.add(href)
            container = h.parent
            print(f"  tag={h.name} parent_class={' '.join(container.get('class', []))[:60]}")
            print(f"  title={h.get_text(strip=True)[:60]}")
            print(f"  href={href[:80]}")
            if len(seen) >= 8:
                break


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
            locale="en-CA",
            timezone_id="America/Toronto",
        )
        page = context.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        for label, url in URLS:
            debug_page(page, label, url)

        browser.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
