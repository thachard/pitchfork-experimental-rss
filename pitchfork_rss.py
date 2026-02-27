#!/usr/bin/env python3
"""
Pitchfork Experimental Reviews – RSS Feed Generator
-----------------------------------------------------
Uses Playwright to render the page, then extracts review cards
using the exact CSS selectors found in Pitchfork's HTML.

Usage:
    pip install playwright beautifulsoup4
    playwright install chromium
    python pitchfork_rss.py
"""

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import json
import sys
import time

BASE_URL = "https://pitchfork.com"
FEED_URL = f"{BASE_URL}/genre/experimental/review/"
OUTPUT_FILE = "feed.xml"


def fetch_reviews():
    print(f"Fetching {FEED_URL} ...")
    reviews = []

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
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

        page = context.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        """)

        page.goto(FEED_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)

        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "html.parser")
    cards = soup.find_all("div", attrs={"data-item": True})
    print(f"  Found {len(cards)} review cards.")

    for card in cards:
        try:
            data = json.loads(card["data-item"])
        except (json.JSONDecodeError, KeyError):
            continue

        link = data.get("hotelLink", "")
        if not link or "reviews/albums" not in link:
            continue

        full_url = BASE_URL + link if link.startswith("/") else link

        title_tag = card.select_one("h3.summary-item__hed")
        title = title_tag.get_text(strip=True) if title_tag else BeautifulSoup(data.get("dangerousHed", "Untitled"), "html.parser").get_text(strip=True)

        artist_tag = card.select_one("div.summary-item__sub-hed")
        artist = artist_tag.get_text(strip=True) if artist_tag else ""

        date_tag = card.select_one("time.summary-item__publish-date")
        pub_date = date_tag.get("datetime", date_tag.get_text(strip=True)) if date_tag else ""

        author_tag = card.select_one("span.byline__name")
        author = author_tag.get_text(strip=True).lstrip("By").strip() if author_tag else "Pitchfork"

        full_title = f"{artist} – {title}" if artist else title

        reviews.append({
            "title": full_title,
            "link": full_url,
            "description": f"A review by {author}" if author else "",
            "pubDate": pub_date,
            "author": author,
        })

    print(f"  Parsed {len(reviews)} album reviews.")
    return reviews


def format_date(pub):
    """Convert a date string to RFC 2822 format required by RSS."""
    if not pub:
        return ""
    # Try ISO format first (e.g. 2026-02-26T00:00:00Z)
    try:
        dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
        return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
    except ValueError:
        pass
    # Try human-readable format as used by Pitchfork (e.g. "February 26, 2026")
    try:
        dt = datetime.strptime(pub.strip(), "%B %d, %Y")
        return dt.strftime("%a, %d %b %Y 00:00:00 +0000")
    except ValueError:
        pass
    return ""


def escape_xml(text):
    """Escape special XML characters."""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
    )


def write_feed(reviews, output_path=OUTPUT_FILE):
    """Write RSS feed as a plain string to avoid ElementTree CDATA issues."""
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        '  <channel>',
        f'    <title>Pitchfork – Experimental Reviews</title>',
        f'    <link>{FEED_URL}</link>',
        f'    <description>Latest experimental album reviews from Pitchfork.</description>',
        f'    <language>en-us</language>',
        f'    <lastBuildDate>{now}</lastBuildDate>',
        f'    <atom:link href="{FEED_URL}" rel="self" type="application/rss+xml"/>',
    ]

    for review in reviews:
        pub = format_date(review.get("pubDate", ""))
        lines += [
            '    <item>',
            f'      <title>{escape_xml(review.get("title", ""))}</title>',
            f'      <link>{escape_xml(review.get("link", ""))}</link>',
            f'      <guid isPermaLink="true">{escape_xml(review.get("link", ""))}</guid>',
            f'      <description>{escape_xml(review.get("description", ""))}</description>',
            f'      <author>{escape_xml(review.get("author", "Pitchfork"))}</author>',
        ]
        if pub:
            lines.append(f'      <pubDate>{pub}</pubDate>')
        lines.append('    </item>')

    lines += ['  </channel>', '</rss>']

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"RSS feed written to: {output_path}")


if __name__ == "__main__":
    reviews = fetch_reviews()
    if not reviews:
        print("No reviews found. The page structure may have changed.", file=sys.stderr)
        sys.exit(1)
    write_feed(reviews)
