#!/usr/bin/env python3
"""
The Metropolitan Review – Nonfiction RSS Feed Generator
------------------------------------------------------
1. Uses Playwright to scrape article URLs from /t/nonfiction listing page
2. Fetches the main Substack feed via feedparser
3. Keeps only feed entries whose URL appears in the fiction listing
4. Writes metropolitan_nonfiction_feed.xml

Usage:
    pip install playwright beautifulsoup4 feedparser
    playwright install chromium
    python metropolitan_fiction_rss.py
"""

import feedparser
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import sys
import time

LISTING_URL = "https://www.metropolitanreview.org/t/nonfiction"
FEED_URL = "https://www.metropolitanreview.org/feed"
OUTPUT_FILE = "metropolitan_nonfiction_feed.xml"
MAX_ARTICLES = 15


def escape_xml(text):
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
    )


def format_rfc2822(entry):
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
    return ""


def fetch_fiction_urls():
    """Scrape the /t/nonfiction listing page and return a set of article URLs."""
    print(f"Fetching fiction listing: {LISTING_URL} ...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()
        page.goto(LISTING_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(4)
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "html.parser")
    urls = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/p/" in href and "metropolitanreview.org" in href:
            # Normalise: strip query strings and trailing slashes
            clean = href.split("?")[0].rstrip("/")
            urls.add(clean)

    print(f"  Found {len(urls)} fiction article URLs on listing page.")
    return urls


def fetch_feed_articles(fiction_urls):
    """Fetch main feed and return entries whose URL is in fiction_urls."""
    print(f"Fetching main feed: {FEED_URL} ...")
    feed = feedparser.parse(FEED_URL)

    if feed.bozo and not feed.entries:
        print(f"Feed parse error: {feed.bozo_exception}", file=sys.stderr)
        sys.exit(1)

    print(f"  Total entries in feed: {len(feed.entries)}")

    articles = []
    for entry in feed.entries:
        link = entry.get("link", "").split("?")[0].rstrip("/")
        if link not in fiction_urls:
            continue

        title = entry.get("title", "").strip()
        description = entry.get("summary", "").strip()
        pub_date = format_rfc2822(entry)

        if not title or not link:
            continue

        articles.append({
            "title": title,
            "link": link,
            "description": description,
            "pubDate": pub_date,
        })

        if len(articles) >= MAX_ARTICLES:
            break

    print(f"  Matched {len(articles)} fiction articles in feed.")
    return articles


def write_feed(articles, output_path=OUTPUT_FILE):
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        '  <channel>',
        '    <title>The Metropolitan Review \u2013 Fiction</title>',
        f'    <link>{LISTING_URL}</link>',
        '    <description>Nonfiction reviews from The Metropolitan Review.</description>',
        '    <language>en</language>',
        f'    <lastBuildDate>{now}</lastBuildDate>',
        f'    <atom:link href="{FEED_URL}" rel="self" type="application/rss+xml"/>',
    ]
    for article in articles:
        lines += [
            '    <item>',
            f'      <title>{escape_xml(article["title"])}</title>',
            f'      <link>{escape_xml(article["link"])}</link>',
            f'      <guid isPermaLink="true">{escape_xml(article["link"])}</guid>',
            f'      <description>{escape_xml(article["description"])}</description>',
        ]
        if article["pubDate"]:
            lines.append(f'      <pubDate>{article["pubDate"]}</pubDate>')
        lines.append('    </item>')
    lines += ['  </channel>', '</rss>']

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"RSS feed written to: {output_path}")


if __name__ == "__main__":
    fiction_urls = fetch_fiction_urls()
    if not fiction_urls:
        print("No fiction URLs found on listing page. Page structure may have changed.", file=sys.stderr)
        sys.exit(1)

    articles = fetch_feed_articles(fiction_urls)
    if not articles:
        print("No fiction articles matched in feed. Feed may only contain recent posts.", file=sys.stderr)
        sys.exit(1)

    write_feed(articles)
