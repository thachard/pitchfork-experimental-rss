#!/usr/bin/env python3
"""
The Quietus – Album of the Week RSS Feed Generator
----------------------------------------------------
Scrapes https://thequietus.com/columns/quietus-reviews/album-of-the-week/
and writes quietus_feed.xml.

Date strategy:
- Fetches the most recent article's date using a fresh browser (avoids Cloudflare)
- Calculates older article dates by subtracting 7 days per position (weekly column)

Usage:
    pip install playwright beautifulsoup4
    playwright install chromium
    python quietus_rss.py
"""

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import json
import re
import sys
import time

BASE_URL = "https://thequietus.com"
FEED_URL = f"{BASE_URL}/columns/quietus-reviews/album-of-the-week/"
OUTPUT_FILE = "quietus_feed.xml"
MAX_ARTICLES = 8


def make_context(playwright):
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


def fetch_listing():
    """Fetch the listing page and return list of {title, description, link}."""
    print(f"Fetching listing page: {FEED_URL}")
    with sync_playwright() as p:
        browser, context = make_context(p)
        page = context.new_page()
        page.goto(FEED_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "html.parser")
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

    print(f"  Found {len(articles)} articles.")
    return articles


def fetch_latest_date(url):
    """Fetch the most recent article with a fresh browser to get its publish date."""
    print(f"  Fetching date from most recent article: {url}")
    with sync_playwright() as p:
        browser, context = make_context(p)
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(4)
        date = page.evaluate("""() => {
            const meta = document.querySelector('meta[property="article:published_time"]');
            if (meta && meta.content) return meta.content;
            const scripts = document.querySelectorAll('script[type="application/ld+json"]');
            for (const s of scripts) {
                try {
                    const data = JSON.parse(s.textContent);
                    const items = Array.isArray(data) ? data : (data['@graph'] || [data]);
                    for (const item of items) {
                        if (item.datePublished) return item.datePublished;
                    }
                } catch(e) {}
            }
            const timeEl = document.querySelector('time[datetime]');
            if (timeEl) return timeEl.getAttribute('datetime');
            return null;
        }""")
        print(f"  Raw date from article: {repr(date)}")
        browser.close()
    return date


def parse_date(raw):
    """Parse any date string to a datetime object."""
    if not raw:
        return None
    raw = raw.strip()
    # Strip ordinal suffixes
    raw = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', raw)
    # ISO 8601
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in ["%d %B %Y", "%a %d %B, %Y", "%a %d %B %Y",
                "%B %d, %Y", "%B %d %Y", "%d %b %Y", "%b %d, %Y"]:
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    print(f"  Warning: could not parse date: {repr(raw)}", file=sys.stderr)
    return None


def format_rfc2822(dt):
    if not dt:
        return ""
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")


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
        '    <title>The Quietus \u2013 Album of the Week</title>',
        f'    <link>{FEED_URL}</link>',
        '    <description>Album of the Week reviews from The Quietus.</description>',
        '    <language>en-gb</language>',
        f'    <lastBuildDate>{now}</lastBuildDate>',
        f'    <atom:link href="{FEED_URL}" rel="self" type="application/rss+xml"/>',
    ]
    for article in articles:
        pub = format_rfc2822(article.get("pubDate"))
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
        print("No articles found.", file=sys.stderr)
        sys.exit(1)

    articles = articles[:MAX_ARTICLES]

    # Get the date of the most recent article with a fresh browser
    raw_date = fetch_latest_date(articles[0]["link"])
    latest_dt = parse_date(raw_date)

    if latest_dt:
        print(f"  Most recent article date: {latest_dt.strftime('%d %B %Y')}")
        # Assign dates by subtracting 7 days per position (weekly column)
        for i, article in enumerate(articles):
            article["pubDate"] = latest_dt - timedelta(weeks=i)
    else:
        print("  Warning: could not determine latest date, feed will have no dates.", file=sys.stderr)
        for article in articles:
            article["pubDate"] = None

    for i, article in enumerate(articles):
        dt = article.get("pubDate")
        date_str = dt.strftime('%d %B %Y') if dt else 'NO DATE'
        print(f"  [{i+1}/{len(articles)}] {article['title'][:50]} → {date_str}")

    write_feed(articles)
