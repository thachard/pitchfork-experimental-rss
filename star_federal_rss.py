#!/usr/bin/env python3
"""
Toronto Star – Federal RSS Feed Generator
---------------------------------------------
Scrapes https://www.thestar.com/politics/federal/
and writes star_federal_feed.xml.

Usage:
    pip install playwright beautifulsoup4
    playwright install chromium
    python star_cityhall_rss.py
"""

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import sys
import time

BASE_URL = "https://www.thestar.com"
FEED_URL = f"{BASE_URL}/politics/federal/"
OUTPUT_FILE = "star_federal_feed.xml"


def fetch_articles():
    print(f"Fetching {FEED_URL} ...")

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
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-CA,en;q=0.9",
            }
        )
        page = context.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-CA', 'en'] });
        """)
        page.goto(FEED_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "html.parser")
    articles = []
    seen = set()

    # Each article card is a div.card-container containing:
    #   div.card-headline (with h3 > a)  — sibling of —  div.card-body (with time.tnt-date)
    for card in soup.find_all("div", class_="card-container"):
        # Date
        time_tag = card.find("time", class_="tnt-date")
        if not time_tag:
            continue
        pub_date = time_tag.get("datetime", "")

        # Heading and link — prefer data-mrf-link for full URL
        heading_tag = card.find(["h2", "h3", "h4"])
        if not heading_tag:
            continue
        a_tag = heading_tag.find("a", href=True)
        if not a_tag:
            continue

        href = a_tag.get("data-mrf-link") or a_tag.get("href", "")
        if not href or href in seen:
            continue
        seen.add(href)

        full_url = BASE_URL + href if href.startswith("/") else href
        title = heading_tag.get_text(strip=True)

        # Description
        desc_tag = card.find("p")
        description = desc_tag.get_text(strip=True) if desc_tag else ""

        articles.append({
            "title": title,
            "link": full_url,
            "description": description,
            "pubDate": pub_date,
        })

    print(f"  Found {len(articles)} articles.")
    return articles


def format_date(pub):
    """Convert ISO date string to RFC 2822 format required by RSS."""
    if not pub:
        return ""
    try:
        dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
        return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
    except ValueError:
        return ""


def escape_xml(text):
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
    )


def write_feed(articles, output_path=OUTPUT_FILE):
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        '  <channel>',
        '    <title>Toronto Star – Federal</title>',
        f'    <link>{FEED_URL}</link>',
        '    <description>Federal politics coverage from the Toronto Star.</description>',
        '    <language>en-ca</language>',
        f'    <lastBuildDate>{now}</lastBuildDate>',
        f'    <atom:link href="{FEED_URL}" rel="self" type="application/rss+xml"/>',
    ]

    for article in articles:
        pub = format_date(article.get("pubDate", ""))
        lines += [
            '    <item>',
            f'      <title>{escape_xml(article.get("title", ""))}</title>',
            f'      <link>{escape_xml(article.get("link", ""))}</link>',
            f'      <guid isPermaLink="true">{escape_xml(article.get("link", ""))}</guid>',
            f'      <description>{escape_xml(article.get("description", ""))}</description>',
        ]
        if pub:
            lines.append(f'      <pubDate>{pub}</pubDate>')
        lines.append('    </item>')

    lines += ['  </channel>', '</rss>']

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"RSS feed written to: {output_path}")


if __name__ == "__main__":
    articles = fetch_articles()
    if not articles:
        print("No articles found. The page structure may have changed.", file=sys.stderr)
        sys.exit(1)
    write_feed(articles)
