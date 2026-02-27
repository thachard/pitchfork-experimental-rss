#!/usr/bin/env python3
"""
FT Fiction – RSS Feed Generator
---------------------------------
Scrapes https://www.ft.com/fiction and writes ft_fiction_feed.xml.
No Playwright needed — the page renders server-side.

Usage:
    pip install requests beautifulsoup4
    python ft_fiction_rss.py
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import sys

BASE_URL = "https://www.ft.com"
FEED_URL = f"{BASE_URL}/fiction"
OUTPUT_FILE = "ft_fiction_feed.xml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_articles():
    print(f"Fetching {FEED_URL} ...")
    resp = requests.get(FEED_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    articles = []
    seen = set()

    # Each article is inside an li.o-teaser-collection__item
    for card in soup.find_all("li", class_="o-teaser-collection__item"):
        # Title and link
        title_tag = card.select_one("a.js-teaser-heading-link")
        if not title_tag:
            continue

        href = title_tag.get("href", "")
        if not href or href in seen:
            continue
        seen.add(href)

        full_url = BASE_URL + href if href.startswith("/") else href
        title = title_tag.get_text(strip=True)

        # Description (standfirst)
        desc_tag = card.select_one("p.o-teaser__standfirst, a.js-teaser-standfirst-link")
        description = desc_tag.get_text(strip=True) if desc_tag else ""

        # Date — already present as ISO datetime attribute
        time_tag = card.select_one("time.o-date")
        pub_date = time_tag.get("datetime", "") if time_tag else ""

        articles.append({
            "title": title,
            "description": description,
            "link": full_url,
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
        '    <title>FT – Fiction</title>',
        f'    <link>{FEED_URL}</link>',
        '    <description>Fiction reviews and articles from the Financial Times.</description>',
        '    <language>en-gb</language>',
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
