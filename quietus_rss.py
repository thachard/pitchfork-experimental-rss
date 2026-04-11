#!/usr/bin/env python3
"""
The Quietus – Album of the Week RSS Feed Generator
----------------------------------------------------
Scrapes https://thequietus.com/columns/quietus-reviews/album-of-the-week/
and fetches each article page for its publish date, then writes quietus_feed.xml.

Uses Playwright for full browser rendering to avoid bot detection.

Usage:
    pip install playwright beautifulsoup4
    playwright install chromium
    python quietus_rss.py
"""

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import json
import re
import sys
import time

BASE_URL = "https://thequietus.com"
FEED_URL = f"{BASE_URL}/columns/quietus-reviews/album-of-the-week/"
OUTPUT_FILE = "quietus_feed.xml"


def make_browser_context(playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
        locale="en-GB",
        extra_http_headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
        }
    )
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-GB', 'en'] });
    """)
    return browser, context


def fetch_listing(page):
    """Fetch the listing page and return list of {title, description, link}."""
    print(f"Fetching {FEED_URL} ...")
    page.goto(FEED_URL, wait_until="domcontentloaded", timeout=60000)
    time.sleep(3)
    soup = BeautifulSoup(page.content(), "html.parser")

    articles = []
    seen = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
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

        h3.extract()
        description = a_tag.get_text(separator=" ", strip=True)

        articles.append({
            "title": title,
            "description": description,
            "link": full_url,
        })

    print(f"  Found {len(articles)} articles on listing page.")
    return articles


def fetch_article_date(page, url):
    """Fetch an individual article page and extract its publish date."""
    try:
        page.goto(url, wait_until="networkidle", timeout=60000)
        time.sleep(2)
        soup = BeautifulSoup(page.content(), "html.parser")

        # 1. Open Graph article:published_time meta tag
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
                    for field in ("datePublished", "dateCreated", "dateModified"):
                        if field in item:
                            return item[field]
            except (json.JSONDecodeError, AttributeError):
                pass

        # 3. <time> tag with datetime attribute
        time_tag = soup.find("time", {"datetime": True})
        if time_tag:
            return time_tag["datetime"]

        # 4. <time> tag text only
        time_tag = soup.find("time")
        if time_tag:
            return time_tag.get_text(strip=True)

        # 5. Regex scan of page text for date patterns
        text = soup.get_text(" ")

        # Quietus-specific: "Published 6:03am 26 February 2026"
        match = re.search(
            r"Published\s+\d{1,2}:\d{2}(?:am|pm)\s+(\d{1,2})\s+"
            r"(January|February|March|April|May|June|"
            r"July|August|September|October|November|December)\s+(\d{4})",
            text, re.IGNORECASE
        )
        if match:
            return f"{match.group(1)} {match.group(2)} {match.group(3)}"

        # Generic: "26 February 2026"
        match = re.search(
            r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|"
            r"July|August|September|October|November|December)\s+(\d{4})\b",
            text
        )
        if match:
            return f"{match.group(1)} {match.group(2)} {match.group(3)}"

        # Generic: "February 26, 2026"
        match = re.search(
            r"\b(January|February|March|April|May|June|July|August|September|"
            r"October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b",
            text
        )
        if match:
            return f"{match.group(1)} {match.group(2)}, {match.group(3)}"

    except Exception as e:
        print(f"  Warning: could not fetch date for {url}: {e}", file=sys.stderr)

    return ""


def format_date(pub):
    """Convert any date string to RFC 2822 format required by RSS."""
    if not pub:
        return ""

    pub = pub.strip()

    # ISO 8601 (e.g. 2026-02-26T10:00:00+00:00 or 2026-02-26)
    try:
        dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
        return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
    except ValueError:
        pass

    formats = [
        "%d %B %Y",        # 26 February 2026
        "%a %d %B, %Y",    # Thu 26 February, 2026
        "%a %d %B %Y",     # Thu 26 February 2026
        "%B %d, %Y",       # February 26, 2026
        "%B %d %Y",        # February 26 2026
        "%d/%m/%Y",        # 26/02/2026
        "%Y/%m/%d",        # 2026/02/26
        "%d-%m-%Y",        # 26-02-2026
        "%b %d, %Y",       # Feb 26, 2026
        "%d %b %Y",        # 26 Feb 2026
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(pub, fmt)
            return dt.strftime("%a, %d %b %Y 00:00:00 +0000")
        except ValueError:
            pass

    # Strip ordinal suffixes and retry
    cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", pub)
    if cleaned != pub:
        return format_date(cleaned)

    print(f"  Warning: could not parse date: {repr(pub)}", file=sys.stderr)
    return ""


def escape_xml(text):
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
    )


def write_feed(reviews, output_path=OUTPUT_FILE):
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        '  <channel>',
        '    <title>The Quietus \u2013 Album of the Week</title>',
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
    with sync_playwright() as p:
        browser, context = make_browser_context(p)
        page = context.new_page()

        articles = fetch_listing(page)
        if not articles:
            print("No articles found. The page structure may have changed.", file=sys.stderr)
            browser.close()
            sys.exit(1)

        articles = articles[:15]
        print(f"Fetching publish dates for {len(articles)} articles...")
        for i, article in enumerate(articles):
            date = fetch_article_date(page, article["link"])
            article["pubDate"] = date
            print(f"  [{i+1}/{len(articles)}] {article['title'][:50]} -> {repr(date) if date else 'NO DATE FOUND'}")
            time.sleep(2)

        browser.close()

    write_feed(articles)
