#!/usr/bin/env python3
"""
The Metropolitan Review – Fiction RSS Feed Generator
------------------------------------------------------
Fetches the main Substack feed and filters to fiction-tagged posts only,
then writes metropolitan_fiction_feed.xml.

Usage:
    pip install feedparser
    python metropolitan_fiction_rss.py
"""

import feedparser
from datetime import datetime, timezone
import sys

FEED_URL = "https://www.metropolitanreview.org/feed"
SOURCE_URL = "https://www.metropolitanreview.org/t/fiction"
OUTPUT_FILE = "metropolitan_fiction_feed.xml"
MAX_ARTICLES = 15
FILTER_TAG = "fiction"


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


def is_fiction(entry):
    """Return True if the entry is tagged with fiction."""
    # feedparser exposes tags as entry.tags list of {term, scheme, label}
    tags = entry.get("tags", [])
    for tag in tags:
        term = tag.get("term", "").lower()
        label = tag.get("label", "").lower()
        if FILTER_TAG in term or FILTER_TAG in label:
            return True
    # Also check category field directly
    category = entry.get("category", "").lower()
    if FILTER_TAG in category:
        return True
    return False


def fetch_articles():
    print(f"Fetching {FEED_URL} ...")
    feed = feedparser.parse(FEED_URL)

    if feed.bozo and not feed.entries:
        print(f"Feed parse error: {feed.bozo_exception}", file=sys.stderr)
        sys.exit(1)

    print(f"  Total entries in feed: {len(feed.entries)}")

    # Debug: show tags on first few entries so we can verify filtering
    for entry in feed.entries[:3]:
        tags = [t.get("term", "") for t in entry.get("tags", [])]
        print(f"  Sample entry: {entry.get('title','')[:50]} | tags: {tags}")

    articles = []
    for entry in feed.entries:
        if not is_fiction(entry):
            continue

        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
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

    print(f"  Found {len(articles)} fiction articles.")
    return articles


def write_feed(articles, output_path=OUTPUT_FILE):
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        '  <channel>',
        '    <title>The Metropolitan Review \u2013 Fiction</title>',
        f'    <link>{SOURCE_URL}</link>',
        '    <description>Fiction reviews from The Metropolitan Review.</description>',
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
    articles = fetch_articles()
    if not articles:
        print("No fiction articles found. Check tag filtering in logs.", file=sys.stderr)
        sys.exit(1)
    write_feed(articles)
