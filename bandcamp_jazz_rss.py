#!/usr/bin/env python3
"""
Bandcamp Daily – Best Jazz RSS Feed Generator
----------------------------------------------
Scrapes https://daily.bandcamp.com/best-jazz and writes bandcamp_jazz_feed.xml.

Usage:
    pip install requests beautifulsoup4
    python bandcamp_jazz_rss.py
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import sys

BASE_URL = "https://daily.bandcamp.com"
FEED_URL = f"{BASE_URL}/best-jazz"
OUTPUT_FILE = "bandcamp_jazz_feed.xml"
MAX_ARTICLES = 15

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_articles():
    print(f"Fetching {FEED_URL} ...")
    resp = requests.get(FEED_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    articles = []
    seen = set()

    # Each article card has: a[href] containing /best-jazz/,
    # a date span, and a title link
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("/best-jazz/"):
            continue
        if href in seen:
            continue

        # Title is the text of the link, skip nav/category links
        title = a.get_text(strip=True)
        if not title or title.upper() == "BEST JAZZ":
            continue

        seen.add(href)
        full_url = BASE_URL + href

        # Date: look in the parent container for a text matching
        # the pattern "Month DD, YYYY"
        parent = a.parent
        pub_date = ""
        # Walk up a few levels to find the date text
        for _ in range(5):
            if parent is None:
                break
            text = parent.get_text(" ", strip=True)
            import re
            m = re.search(
                r'(January|February|March|April|May|June|July|August|'
                r'September|October|November|December)\s+\d{1,2},\s+\d{4}',
                text
            )
            if m:
                pub_date = m.group(0)
                break
            parent = parent.parent

        articles.append({
            "title": title,
            "link": full_url,
            "description": "",
            "pubDate": pub_date,
        })

        if len(articles) >= MAX_ARTICLES:
            break

    print(f"  Found {len(articles)} articles.")
    return articles


def format_date(pub):
    if not pub:
        return ""
    try:
        dt = datetime.strptime(pub, "%B %d, %Y")
        return dt.replace(tzinfo=timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
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
        '    <title>Bandcamp Daily \u2013 Best Jazz</title>',
        f'    <link>{FEED_URL}</link>',
        '    <description>Monthly best jazz roundups from Bandcamp Daily.</description>',
        '    <language>en</language>',
        f'    <lastBuildDate>{now}</lastBuildDate>',
        f'    <atom:link href="{FEED_URL}" rel="self" type="application/rss+xml"/>',
    ]
    for article in articles:
        pub = format_date(article["pubDate"])
        lines += [
            '    <item>',
            f'      <title>{escape_xml(article["title"])}</title>',
            f'      <link>{escape_xml(article["link"])}</link>',
            f'      <guid isPermaLink="true">{escape_xml(article["link"])}</guid>',
            f'      <description>{escape_xml(article["description"])}</description>',
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
        print("No articles found.", file=sys.stderr)
        sys.exit(1)
    write_feed(articles)
