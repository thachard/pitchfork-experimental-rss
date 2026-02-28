#!/usr/bin/env python3
"""
CTV News – Queen's Park RSS Feed Generator
--------------------------------------------
Scrapes https://www.ctvnews.ca/toronto/politics/queens-park/
fetches each article page for its publish date, and writes ctv_queenspark_feed.xml.
No Playwright needed — the listing page renders server-side.

Usage:
    pip install requests beautifulsoup4
    python ctv_queenspark_rss.py
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import json
import sys
import time

BASE_URL = "https://www.ctvnews.ca"
FEED_URL = f"{BASE_URL}/toronto/politics/queens-park/"
OUTPUT_FILE = "ctv_queenspark_feed.xml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-CA,en;q=0.9",
}


def fetch_listing():
    """Fetch the listing page and extract article titles, links and descriptions."""
    print(f"Fetching {FEED_URL} ...")
    resp = requests.get(FEED_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    articles = []
    seen = set()

    # Each article has an h2 with a link, followed by a paragraph description
    for h2 in soup.find_all("h2"):
        a_tag = h2.find("a", href=True)
        if not a_tag:
            continue

        href = a_tag["href"]
        if href in seen:
            continue

        # Only article links, not section nav links
        if "/article/" not in href:
            continue

        seen.add(href)
        full_url = BASE_URL + href if href.startswith("/") else href
        title = a_tag.get_text(strip=True)

        # Description is typically a sibling <p> or an <a> inside a sibling tag
        description = ""
        next_sib = h2.find_next_sibling()
        if next_sib:
            description = next_sib.get_text(strip=True)

        articles.append({
            "title": title,
            "link": full_url,
            "description": description,
        })

    print(f"  Found {len(articles)} articles.")
    return articles


def fetch_article_date(url):
    """Fetch an individual article and extract its publish date."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # 1. article:published_time meta tag (standard on Arc Publishing sites)
        for prop in ["article:published_time", "article:published", "og:published_time"]:
            meta = soup.find("meta", {"property": prop})
            if meta and meta.get("content"):
                return meta["content"]

        # 2. JSON-LD structured data
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    for field in ("datePublished", "dateCreated"):
                        if field in item:
                            return item[field]
            except (json.JSONDecodeError, AttributeError):
                pass

        # 3. <time> tag with datetime attribute
        time_tag = soup.find("time", {"datetime": True})
        if time_tag:
            return time_tag["datetime"]

    except Exception as e:
        print(f"  Warning: could not fetch date for {url}: {e}", file=sys.stderr)

    return ""


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
        "    <title>CTV News – Queen's Park</title>",
        f'    <link>{FEED_URL}</link>',
        "    <description>Queen's Park coverage from CTV News Toronto.</description>",
        '    <language>en-ca</language>',
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
    articles = fetch_listing()
    if not articles:
        print("No articles found. The page structure may have changed.", file=sys.stderr)
        sys.exit(1)

    # Fetch publish date from each article, limit to 15 most recent
    articles = articles[:15]
    print(f"Fetching publish dates for {len(articles)} articles...")
    for i, article in enumerate(articles):
        date = fetch_article_date(article["link"])
        article["pubDate"] = date
        print(f"  [{i+1}/{len(articles)}] {article['title'][:50]} → {date or 'NO DATE FOUND'}")
        time.sleep(0.5)

    write_feed(articles)
