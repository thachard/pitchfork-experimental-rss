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
from xml.etree.ElementTree import Element, SubElement, tostring
import xml.dom.minidom
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

    # Each review card has a data-item attribute with the link
    cards = soup.find_all("div", attrs={"data-item": True})
    print(f"  Found {len(cards)} review cards.")

    for card in cards:
        try:
            data = json.loads(card["data-item"])
        except (json.JSONDecodeError, KeyError):
            continue

        link = data.get("hotelLink", "")
        if not link:
            continue

        # Only include album reviews
        if "reviews/albums" not in link:
            continue

        full_url = BASE_URL + link if link.startswith("/") else link

        # Title: inside h3.summary-item__hed
        title_tag = card.select_one("h3.summary-item__hed")
        title = title_tag.get_text(strip=True) if title_tag else data.get("dangerousHed", "Untitled")
        # Strip any HTML tags that may be in dangerousHed fallback
        title = BeautifulSoup(title, "html.parser").get_text(strip=True)

        # Artist: inside div.summary-item__sub-hed
        artist_tag = card.select_one("div.summary-item__sub-hed")
        artist = artist_tag.get_text(strip=True) if artist_tag else ""

        # Date: inside time.summary-item__publish-date
        date_tag = card.select_one("time.summary-item__publish-date")
        pub_date = date_tag.get("datetime", date_tag.get_text(strip=True)) if date_tag else ""

        # Author: inside span.byline__name
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


def build_rss(reviews):
    rss = Element("rss", version="2.0")
    rss.set("xmlns:atom", "http://www.w3.org/2005/Atom")

    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = "Pitchfork – Experimental Reviews"
    SubElement(channel, "link").text = FEED_URL
    SubElement(channel, "description").text = "Latest experimental album reviews from Pitchfork."
    SubElement(channel, "language").text = "en-us"
    SubElement(channel, "lastBuildDate").text = (
        datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    )

    atom_link = SubElement(channel, "atom:link")
    atom_link.set("href", FEED_URL)
    atom_link.set("rel", "self")
    atom_link.set("type", "application/rss+xml")

    for review in reviews:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = review.get("title", "")
        SubElement(item, "link").text = review.get("link", "")
        SubElement(item, "description").text = review.get("description", "")
        SubElement(item, "author").text = review.get("author", "Pitchfork")
        SubElement(item, "guid", isPermaLink="true").text = review.get("link", "")

        pub = review.get("pubDate", "")
        if pub:
            try:
                dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                pub = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
            except ValueError:
                pass
            SubElement(item, "pubDate").text = pub

    return rss


def write_feed(rss_element, output_path=OUTPUT_FILE):
    raw = tostring(rss_element, encoding="unicode", xml_declaration=False)
    pretty = xml.dom.minidom.parseString(
        '<?xml version="1.0" encoding="UTF-8"?>' + raw
    ).toprettyxml(indent="  ", encoding=None)
    lines = pretty.split("\n")
    if lines[0].startswith("<?xml"):
        lines = lines[1:]
    final = '<?xml version="1.0" encoding="UTF-8"?>\n' + "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final)
    print(f"RSS feed written to: {output_path}")


if __name__ == "__main__":
    reviews = fetch_reviews()
    if not reviews:
        print("No reviews found. The page structure may have changed.", file=sys.stderr)
        sys.exit(1)
    rss = build_rss(reviews)
    write_feed(rss)
