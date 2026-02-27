#!/usr/bin/env python3
"""
The Quietus – Album of the Week RSS Feed Generator
----------------------------------------------------
Scrapes https://thequietus.com/columns/quietus-reviews/album-of-the-week/
and fetches each article page for its publish date, then writes feed.xml.

Usage:
    pip install requests beautifulsoup4
    python quietus_rss.py
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import sys
import time

BASE_URL = "https://thequietus.com"
FEED_URL = f"{BASE_URL}/columns/quietus-reviews/album-of-the-week/"
OUTPUT_FILE = "quietus_feed.xml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_listing():
    """Fetch the listing page and return list of {title, description, link}."""
    print(f"Fetching {FEED_URL} ...")
    resp = requests.get(FEED_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    articles = []
    seen = set()

    # Each article link contains an <h3> title and description text
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        # Only article links (not category nav links)
        if "quietus-reviews/album-of-the-week/" not in href:
            continue
        if href in seen:
            continue

        h3 = a_tag.find("h3")
        if not h3:
            continue

        seen.add(href)
        full_url = href if href.startswith("http") else BASE_URL + href
        title = h3.get_text(strip=True)

        # Description is the remaining text in the link after the h3
        h3.extract()
        description = a_tag.get_text(separator=" ", strip=True)

        articles.append({
            "title": title,
            "description": description,
            "link": full_url,
        })

    print(f"  Found {len(articles)} articles on listing page.")
    return articles


def fetch_article_date(url):
    """Fetch an individual article page and return its publish date string."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # WordPress typically uses <time datetime="..."> 
        time_tag = soup.find("time")
        if time_tag:
            # Prefer machine-readable datetime attribute
            dt_attr = time_tag.get("datetime", "")
            if dt_attr:
                return dt_attr
            # Fall back to text content
            return time_tag.get_text(strip=True)

        # Fallback: look for a date in a meta tag
        meta = soup.find("meta", {"property": "article:published_time"})
        if meta:
            return meta.get("content", "")

    except Exception as e:
        print(f"  Warning: could not fetch date for {url}: {e}", file=sys.stderr)
    return ""


def format_date(pub):
    """Convert a date string to RFC 2822 format required by RSS."""
    if not pub:
        return ""
    # Try ISO format (e.g. 2026-02-26T10:00:00+00:00 or 2026-02-26)
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            pub_clean = pub.replace("Z", "+00:00")
            dt = datetime.fromisoformat(pub_clean)
            return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
        except ValueError:
            pass
    # Try human-readable (e.g. "26 February 2026" or "February 26, 2026")
    for fmt in ("%d %B %Y", "%B %d, %Y"):
        try:
            dt = datetime.strptime(pub.strip(), fmt)
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
    """Write RSS feed as a plain string."""
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        '  <channel>',
        '    <title>The Quietus – Album of the Week</title>',
        f'    <link>{FEED_URL}</link>',
        '    <description>Album of the Week reviews from The Quietus.</description>',
        '    <language>en-gb</language>',
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
        ]
        if pub:
            lines.append(f'      <pubDate>{pub}</pubDate>')
        lines.append('    </item>')

    lines += ['  </channel>', '</rss>']

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"RSS feed written to: {output_path}")


if __name__ == "__main__":
    articles = fetch_listing()
    if not articles:
        print("No articles found. The page structure may have changed.", file=sys.stderr)
        sys.exit(1)

    # Fetch publish date from each individual article page
    # Only process the most recent 15 to keep things fast
    articles = articles[:15]
    print(f"Fetching publish dates for {len(articles)} articles...")
    for i, article in enumerate(articles):
        date = fetch_article_date(article["link"])
        article["pubDate"] = date
        print(f"  [{i+1}/{len(articles)}] {article['title'][:50]} → {date or 'no date found'}")
        time.sleep(0.5)  # Be polite, don't hammer the server

    write_feed(articles)
