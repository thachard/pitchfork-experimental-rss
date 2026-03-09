#!/usr/bin/env python3
"""
Meta Feed Merger
-----------------
Fetches multiple RSS feeds, filters to recent articles, deduplicates by
comparing article descriptions and titles, and outputs one merged RSS feed
per group.

Deduplication uses the feed's own description/summary field (no page fetching
required), with a title-similarity fallback for entries with short descriptions.

CONFIGURATION: Edit the FEED_GROUPS and LOOKBACK_DAYS variables below.

Usage:
    pip install feedparser beautifulsoup4
    python merge_feeds.py
"""

from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from xml.sax.saxutils import escape as xml_escape
import feedparser
import sys

# =============================================================================
# CONFIGURATION — edit this section
# =============================================================================

LOOKBACK_DAYS = 3  # Only include articles published within this many days

FEED_GROUPS = [
    {
        "name": "Canada",
        "output": "Canada_feed.xml",
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
            "https://raw.githubusercontent.com/thachard/pitchfork-experimental-rss/main/ctv_cityhall_feed.xml",
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
            "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
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
            "https://thelogic.co/tag/tech/feed",
        ],
    },
]

# Similarity thresholds
# Description-based: higher threshold since descriptions are shorter and noisier
DESCRIPTION_SIMILARITY_THRESHOLD = 0.75
# Title-based: used as fallback when descriptions are too short to compare
TITLE_SIMILARITY_THRESHOLD = 0.80
# Minimum description length (chars) to use description-based dedup;
# below this we fall back to title comparison
MIN_DESCRIPTION_LENGTH = 80

# Max articles to fetch per feed (keeps run times reasonable)
MAX_ARTICLES_PER_FEED = 20

# Request headers for feed fetching
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


def clean_html(raw_html):
    """Strip HTML tags and collapse whitespace from a string."""
    if not raw_html:
        return ""
    return BeautifulSoup(raw_html, "html.parser").get_text(separator=" ", strip=True)


def similarity(a, b):
    """Return a similarity ratio between two strings."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def is_duplicate(article, seen_articles):
    """
    Check if an article is a duplicate of any already-seen article.

    Strategy:
    - If description is long enough, compare descriptions.
    - Otherwise, compare titles.
    - Returns True if either check exceeds its threshold.
    """
    desc = article["description"]
    title = article["title"]

    for seen in seen_articles:
        # Try description-based comparison if both are long enough
        if (
            len(desc) >= MIN_DESCRIPTION_LENGTH
            and len(seen["description"]) >= MIN_DESCRIPTION_LENGTH
        ):
            if similarity(desc, seen["description"]) >= DESCRIPTION_SIMILARITY_THRESHOLD:
                return True
        # Always also check title similarity as a catch-all
        if similarity(title, seen["title"]) >= TITLE_SIMILARITY_THRESHOLD:
            return True

    return False


def format_date(dt):
    """Convert datetime to RFC 2822 string for RSS."""
    if not dt:
        return ""
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")


def write_feed(group_name, output_path, articles):
    """Write a list of article dicts to an RSS XML file."""
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "  <channel>",
        f"    <title>{xml_escape(group_name)} – Merged Feed</title>",
        "    <link>https://github.com</link>",
        f"    <description>Deduplicated merged feed for {xml_escape(group_name)}.</description>",
        "    <language>en</language>",
        f"    <lastBuildDate>{now}</lastBuildDate>",
    ]

    for article in articles:
        pub = format_date(article.get("pubDate"))
        lines += [
            "    <item>",
            f'      <title>{xml_escape(article.get("title", ""))}</title>',
            f'      <link>{xml_escape(article.get("link", ""))}</link>',
            f'      <guid isPermaLink="true">{xml_escape(article.get("link", ""))}</guid>',
            f'      <description>{xml_escape(article.get("description", ""))}</description>',
        ]
        if pub:
            lines.append(f"      <pubDate>{pub}</pubDate>")
        lines.append("    </item>")

    lines += ["  </channel>", "</rss>"]

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
            description = clean_html(entry.get("summary", ""))

            all_articles.append(
                {
                    "title": title,
                    "link": link,
                    "description": description,
                    "pubDate": pub_date,
                    "source_feed": url,
                }
            )
            count += 1

        print(f"    {count} recent articles from {url}")

    if not all_articles:
        print("  No recent articles found across all feeds.")
        write_feed(name, output, [])
        return

    # Step 2: Sort oldest-first so we keep the earliest version of each story
    all_articles.sort(
        key=lambda a: a["pubDate"] or datetime.min.replace(tzinfo=timezone.utc)
    )

    # Step 3: Deduplicate — iterate oldest-first, keep earliest unique story
    print(f"\n  Deduplicating {len(all_articles)} articles...")
    unique_articles = []

    for article in all_articles:
        if is_duplicate(article, unique_articles):
            print(f"    DUPLICATE skipped: {article['title'][:60]}")
        else:
            unique_articles.append(article)

    # Sort final list newest-first for the RSS feed
    unique_articles.sort(
        key=lambda a: a["pubDate"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    print(f"\n  {len(all_articles)} total → {len(unique_articles)} after deduplication")
    write_feed(name, output, unique_articles)


def main():
    print("Meta Feed Merger")
    print(
        f"Lookback: {LOOKBACK_DAYS} days | "
        f"Description threshold: {DESCRIPTION_SIMILARITY_THRESHOLD} | "
        f"Title threshold: {TITLE_SIMILARITY_THRESHOLD}"
    )

    for group in FEED_GROUPS:
        process_group(group)

    print("\nDone.")


if __name__ == "__main__":
    main()
