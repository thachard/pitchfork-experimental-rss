#!/usr/bin/env python3
"""
Meta Feed Merger
-----------------
Fetches multiple RSS feeds, filters to recent articles, deduplicates by
comparing the first body paragraph of each article, and outputs one merged
RSS feed per group.

CONFIGURATION: Edit the FEED_GROUPS and LOOKBACK_DAYS variables below.

Usage:
    pip install requests beautifulsoup4 feedparser
    python merge_feeds.py
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
import feedparser
import sys
import time

# =============================================================================
# CONFIGURATION — edit this section
# =============================================================================

LOOKBACK_DAYS = 3  # Only include articles published within this many days

FEED_GROUPS = [
    {
        "name": "Canada",           # Human-readable name for this group
        "output": "Canada_feed.xml", # Output filename
        "feeds": [
            "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/politics/",
            "https://raw.githubusercontent.com/thachard/pitchfork-experimental-rss/main/star_ontario_feed.xml",
            "https://raw.githubusercontent.com/thachard/pitchfork-experimental-rss/main/star_federal_feed.xml",
            "https://globalnews.ca/politics/feed/",
            "https://www.cbc.ca/webfeed/rss/rss-politics",
            "https://thelogic.co/tag/national/feed",
            "https://paulwells.substack.com/feed/",
            "https://raw.githubusercontent.com/thachard/pitchfork-experimental-rss/main/star_cityhall_feed.xml",
            "https://raw.githubusercontent.com/thachard/pitchfork-experimental-rss/main/ctv_queenspark_feed.xml",
            "https://raw.githubusercontent.com/thachard/pitchfork-experimental-rss/main/ctv_cityhall_feed.xml"
        ],
    },
    {
        "name": "World",
        "output": "world_feed.xml",
        "feeds": [
           "https://www.ft.com/world?format=rss",
           "https://www.economist.com/europe/rss.xml",
           "https://www.economist.com/middle-east-and-africa/rss.xml",
           "https://www.economist.com/asia/rss.xml",
           "https://www.economist.com/the-americas/rss.xml",
           "https://www.economist.com/china/rss.xml",
           "http://feeds.bbci.co.uk/news/world/europe/rss.xml",
           "https://www.economist.com/leaders/rss.xml",
           "https://www.newyorker.com/contributors/susan-b-glasser/feed",
           "http://feeds.bbci.co.uk/news/world/latin_america/rss.xml",
           "http://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
           "http://feeds.bbci.co.uk/news/world/asia/rss.xml",
           "http://feeds.bbci.co.uk/news/world/africa/rss.xml",
           "http://feeds.bbci.co.uk/news/politics/rss.xml",
           "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"
        ],
    },
    {
        "name": "Economics",
        "output": "economics_feed.xml",
        "feeds": [
            "https://www.newyorker.com/contributors/john-cassidy/feed",
            "https://www.economist.com/finance-and-economics/rss.xml",
            "https://www.economist.com/business/rss.xml",
            "https://www.ft.com/myft/following/92769845-07af-4f2f-a550-87d213fed171.rss",
            "https://www.ft.com/markets?format=rss",
            "https://www.ft.com/companies?format=rss",
            "https://www.ft.com/climate-capital?format=rss",
            "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/business/",
            "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/business/economy/",
            "https://thelogic.co/tag/business/feed",
            "https://adamtooze.substack.com/feed/",
            "https://thelogic.co/tag/tech/feed"
        ],
    },
]

# Similarity threshold: 0.0 = anything matches, 1.0 = must be identical.
# 0.75 catches wire stories reworded across outlets.
SIMILARITY_THRESHOLD = 0.75

# Max articles to fetch per feed (keeps run times reasonable)
MAX_ARTICLES_PER_FEED = 20

# Seconds to wait between article page fetches (be polite to servers)
FETCH_DELAY = 0.5

# =============================================================================
# END OF CONFIGURATION
# =============================================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def parse_date(entry):
    """Extract a timezone-aware datetime from a feedparser entry."""
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        val = getattr(entry, field, None)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def fetch_feed(url):
    """Fetch and parse an RSS feed. Returns list of feedparser entries."""
    try:
        print(f"  Fetching feed: {url}")
        parsed = feedparser.parse(url, request_headers=HEADERS)
        if parsed.bozo and not parsed.entries:
            print(f"    Warning: feed parse error for {url}", file=sys.stderr)
            return []
        return parsed.entries
    except Exception as e:
        print(f"    Warning: could not fetch feed {url}: {e}", file=sys.stderr)
        return []


def fetch_first_paragraph(url):
    """
    Fetch an article page and return the text of its first substantive
    body paragraph. Returns empty string on any failure.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove boilerplate elements
        for tag in soup(["script", "style", "nav", "header", "footer",
                          "aside", "figure", "figcaption", "noscript"]):
            tag.decompose()

        # Try common article body selectors first
        body = (
            soup.select_one("article")
            or soup.select_one("[class*='article-body']")
            or soup.select_one("[class*='story-body']")
            or soup.select_one("[class*='post-body']")
            or soup.select_one("[class*='entry-content']")
            or soup.select_one("main")
            or soup.body
        )

        if not body:
            return ""

        # Find first paragraph with meaningful text (>= 60 chars)
        for p in body.find_all("p"):
            text = p.get_text(separator=" ", strip=True)
            if len(text) >= 60:
                return text

    except Exception as e:
        print(f"    Warning: could not fetch article {url}: {e}", file=sys.stderr)

    return ""


def similarity(a, b):
    """Return a similarity ratio between two strings."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def is_duplicate(paragraph, seen_paragraphs):
    """Return True if paragraph is too similar to any already-seen paragraph."""
    for seen in seen_paragraphs:
        if similarity(paragraph, seen) >= SIMILARITY_THRESHOLD:
            return True
    return False


def format_date(dt):
    """Convert datetime to RFC 2822 string for RSS."""
    if not dt:
        return ""
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")


def escape_xml(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def write_feed(group_name, output_path, articles):
    """Write a list of article dicts to an RSS XML file."""
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        '  <channel>',
        f'    <title>{escape_xml(group_name)} – Merged Feed</title>',
        f'    <link>https://github.com</link>',
        f'    <description>Deduplicated merged feed for {escape_xml(group_name)}.</description>',
        '    <language>en</language>',
        f'    <lastBuildDate>{now}</lastBuildDate>',
    ]

    for article in articles:
        pub = format_date(article.get("pubDate"))
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
    print(f"  Written {len(articles)} articles to {output_path}")


def process_group(group):
    """Fetch, filter, deduplicate and write a feed group."""
    name = group["name"]
    output = group["output"]
    feed_urls = group["feeds"]

    print(f"\n{'='*60}")
    print(f"Processing: {name}")
    print(f"{'='*60}")

    if not feed_urls:
        print("  No feeds configured for this group, skipping.")
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    all_articles = []

    # Step 1: Collect all articles from all feeds in this group
    for url in feed_urls:
        entries = fetch_feed(url)
        count = 0
        for entry in entries[:MAX_ARTICLES_PER_FEED]:
            pub_date = parse_date(entry)

            # Skip if too old
            if pub_date and pub_date < cutoff:
                continue

            link = entry.get("link", "")
            if not link:
                continue

            title = entry.get("title", "Untitled")
            description = BeautifulSoup(
                entry.get("summary", ""), "html.parser"
            ).get_text(strip=True)

            all_articles.append({
                "title": title,
                "link": link,
                "description": description,
                "pubDate": pub_date,
                "source_feed": url,
                "first_paragraph": None,  # Fetched below
            })
            count += 1

        print(f"    {count} recent articles from {url}")

    if not all_articles:
        print("  No recent articles found across all feeds.")
        write_feed(name, output, [])
        return

    # Step 2: Sort by date descending (newest first) so we keep the
    # earliest version when deduplicating (we reverse before dedup below)
    all_articles.sort(key=lambda a: a["pubDate"] or datetime.min.replace(tzinfo=timezone.utc))

    # Step 3: Fetch first paragraph for each article
    print(f"\n  Fetching first paragraphs for {len(all_articles)} articles...")
    for i, article in enumerate(all_articles):
        paragraph = fetch_first_paragraph(article["link"])
        article["first_paragraph"] = paragraph
        status = f"({len(paragraph)} chars)" if paragraph else "(none)"
        print(f"    [{i+1}/{len(all_articles)}] {article['title'][:50]:.50} {status}")
        time.sleep(FETCH_DELAY)

    # Step 4: Deduplicate — iterate oldest-first, keep earliest unique story
    print(f"\n  Deduplicating...")
    seen_paragraphs = []
    unique_articles = []

    for article in all_articles:  # already sorted oldest-first
        para = article["first_paragraph"]
        if not para:
            # No paragraph fetched — include it rather than risk losing content
            unique_articles.append(article)
            continue

        if is_duplicate(para, seen_paragraphs):
            print(f"    DUPLICATE skipped: {article['title'][:60]:.60}")
        else:
            seen_paragraphs.append(para)
            unique_articles.append(article)

    # Sort final list newest-first for the RSS feed
    unique_articles.sort(
        key=lambda a: a["pubDate"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True
    )

    print(f"\n  {len(all_articles)} total → {len(unique_articles)} after deduplication")
    write_feed(name, output, unique_articles)


def main():
    print(f"Meta Feed Merger")
    print(f"Lookback: {LOOKBACK_DAYS} days | Similarity threshold: {SIMILARITY_THRESHOLD}")

    for group in FEED_GROUPS:
        process_group(group)

    print("\nDone.")


if __name__ == "__main__":
    main()
