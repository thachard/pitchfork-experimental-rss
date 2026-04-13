#!/usr/bin/env python3
"""
Los Angeles Review of Books – Reviews RSS Feed Generator
---------------------------------------------------------
Scrapes https://lareviewofbooks.org/articles/reviews/ directly for
titles, links, dates, and descriptions, then writes larb_reviews_feed.xml.

Usage:
    pip install playwright beautifulsoup4
    playwright install chromium
    python larb_reviews_rss.py
"""

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import re
import sys
import time

LISTING_URL = "https://lareviewofbooks.org/articles/reviews/"
BASE_URL = "https://lareviewofbooks.org"
OUTPUT_FILE = "larb_reviews_feed.xml"
MAX_ARTICLES = 15


def fetch_articles():
    print(f"Fetching {LISTING_URL} ...")
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

    # Debug: show a sample article container to understand structure
    article_links = [a for a in soup.find_all("a", href=True)
                     if a["href"].startswith("/article/")]
    print(f"  Article links found: {len(article_links)}")
    if article_links:
        sample = article_links[0]
        print(f"  Sample link text: {sample.get_text(strip=True)[:80]}")
        print(f"  Sample parent tag: {sample.parent.name}")
        print(f"  Sample parent class: {sample.parent.get('class')}")
        print(f"  Sample grandparent html: {str(sample.parent.parent)[:400]}")

    articles = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("/article/"):
            continue
        if href in seen:
            continue

        full_url = BASE_URL + href
        seen.add(href)

        # Walk up to find the card container (has both image link and title)
        container = a.parent
        for _ in range(8):
            if container is None:
                break
            # Title: look for any heading tag in the container
            heading = container.find(["h1", "h2", "h3", "h4"])
            if heading:
                break
            container = container.parent

        if not container:
            continue

        title = heading.get_text(strip=True) if heading else ""
        if not title:
            continue

        # Date: scan container text for date pattern
        pub_date = ""
        text = container.get_text(" ", strip=True)
        m = re.search(
            r'(January|February|March|April|May|June|July|August|'
            r'September|October|November|December)\s+\d{1,2}(?:,\s+\d{4})?',
            text
        )
        if m:
            pub_date = m.group(0)

        # Description: look for a <p> tag in container
        p_tag = container.find("p")
        description = p_tag.get_text(strip=True) if p_tag else ""

        articles.append({
            "title": title,
            "link": full_url,
            "description": description,
            "pubDate": pub_date,
        })

        if len(articles) >= MAX_ARTICLES:
            break

    print(f"  Found {len(articles)} articles.")
    for a in articles[:3]:
        print(f"  {a['title'][:60]} | {a['pubDate']}")
    return articles


def format_date(pub):
    if not pub:
        return ""
    # Add current year if missing
    if not re.search(r'\d{4}', pub):
        pub = pub + f", {datetime.now().year}"
    for fmt in ["%B %d, %Y", "%B %d %Y"]:
        try:
            dt = datetime.strptime(pub.strip(), fmt)
            return dt.replace(tzinfo=timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
        except ValueError:
            pass
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
        '    <title>Los Angeles Review of Books \u2013 Reviews</title>',
        f'    <link>{LISTING_URL}</link>',
        '    <description>Book reviews from the Los Angeles Review of Books.</description>',
        '    <language>en</language>',
        f'    <lastBuildDate>{now}</lastBuildDate>',
        f'    <atom:link href="{LISTING_URL}" rel="self" type="application/rss+xml"/>',
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
        print("No articles found. Check debug output above.", file=sys.stderr)
        sys.exit(1)
    write_feed(articles)
