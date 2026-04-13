#!/usr/bin/env python3
"""
Los Angeles Review of Books – Reviews RSS Feed Generator
---------------------------------------------------------
1. Uses Playwright to scrape article URLs from /articles/reviews/ listing
2. Fetches the main LARB feed via feedparser
3. Keeps only feed entries whose URL appears in the reviews listing
4. Writes larb_reviews_feed.xml

Usage:
    pip install playwright beautifulsoup4 feedparser
    playwright install chromium
    python larb_reviews_rss.py
"""

import feedparser
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import sys
import time

LISTING_URL = "https://lareviewofbooks.org/articles/reviews/"
FEED_URL = "https://lareviewofbooks.org/feed"
OUTPUT_FILE = "larb_reviews_feed.xml"
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


def fetch_review_urls():
    """Scrape the reviews listing page and return a set of article URLs."""
    print(f"Fetching reviews listing: {LISTING_URL} ...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)
        page = context.new_page()
        page.goto(LISTING_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(4)
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "html.parser")

    # Debug: show sample links
    all_links = [a["href"] for a in soup.find_all("a", href=True)
                 if "lareviewofbooks.org" in a["href"] or a["href"].startswith("/")]
    print(f"  Total links on page: {len(all_links)}")
    for l in all_links[:10]:
        print(f"    {l}")

    urls = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # LARB article URLs follow /article/slug/ pattern
        if href.startswith("/article/") or "/article/" in href:
            clean = href.split("?")[0].rstrip("/")
            if not clean.startswith("http"):
                clean = "https://lareviewofbooks.org" + clean
            urls.add(clean)

    # Debug: show what we found
    print(f"  Found {len(urls)} review article URLs.")
    for u in list(urls)[:5]:
        print(f"    {u}")
    return urls


def fetch_feed_articles(review_urls):
    """Fetch main feed and return entries whose URL is in review_urls."""
    print(f"Fetching main feed: {FEED_URL} ...")
    feed = feedparser.parse(FEED_URL)

    # feedparser sets bozo=True for malformed XML but may still have entries
    if feed.bozo:
        print(f"  Feed warning (may still have entries): {feed.bozo_exception}", file=sys.stderr)
    if not feed.entries:
        print("Feed returned no entries.", file=sys.stderr)
        sys.exit(1)

    print(f"  Total entries in feed: {len(feed.entries)}")
    for entry in feed.entries[:3]:
        print(f"  Sample feed link: {entry.get('link', '')}")

    articles = []
    for entry in feed.entries:
        link = entry.get("link", "").split("?")[0].rstrip("/")
        if link not in review_urls:
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

    print(f"  Matched {len(articles)} review articles in feed.")
    return articles


def write_feed(articles, output_path=OUTPUT_FILE):
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        '  <channel>',
        '    <title>Los Angeles Review of Books \u2013 Reviews</title>',
        f'    <link>{LISTING_URL}</link>',
        '    <description>Book reviews from the Los Angeles Review of Books.</description>',
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
    review_urls = fetch_review_urls()
    if not review_urls:
        print("No review URLs found. Check debug output above.", file=sys.stderr)
        sys.exit(1)

    articles = fetch_feed_articles(review_urls)
    if not articles:
        print("No articles matched between listing and feed. Check debug output above.", file=sys.stderr)
        sys.exit(1)

    write_feed(articles)
