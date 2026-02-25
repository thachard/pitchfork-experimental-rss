#!/usr/bin/env python3
"""
Pitchfork Experimental Reviews – RSS Feed Generator
-----------------------------------------------------
Uses Playwright to render the JavaScript-heavy Pitchfork page, then
extracts album review links and writes feed.xml.

Usage:
    pip install playwright beautifulsoup4
    playwright install chromium
    python pitchfork_rss.py
"""

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from xml.etree.ElementTree import Element, SubElement, tostring
import xml.dom.minidom
import json
import sys

BASE_URL = "https://pitchfork.com"
FEED_URL = f"{BASE_URL}/genre/experimental/review/"
OUTPUT_FILE = "feed.xml"


def fetch_reviews():
    """Use a headless browser to render the page and extract reviews."""
    print(f"Fetching {FEED_URL} ...")
    reviews = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page.goto(FEED_URL, wait_until="networkidle", timeout=30000)

        # Try to extract from __NEXT_DATA__ JSON blob first
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")

        next_data_tag = soup.find("script", id="__NEXT_DATA__")
        if next_data_tag:
            try:
                data = json.loads(next_data_tag.string)
                results = (
                    data.get("props", {})
                        .get("pageProps", {})
                        .get("urqlState", {})
                )
                for key, val in results.items():
                    if not isinstance(val, dict):
                        continue
                    content = val.get("data", {})
                    if not isinstance(content, dict):
                        continue
                    for field in ("albumreviews", "reviews", "items"):
                        items = content.get(field, {})
                        if isinstance(items, dict):
                            items = items.get("items", [])
                        if isinstance(items, list) and items:
                            for item in items:
                                review = parse_review_item(item)
                                if review:
                                    reviews.append(review)
                            if reviews:
                                break
                    if reviews:
                        break
            except (json.JSONDecodeError, AttributeError) as e:
                print(f"  JSON parse warning: {e}", file=sys.stderr)

        # Fallback: scan all <a> tags for review links
        if not reviews:
            print("  Falling back to link scraping...")
            seen = set()
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                full_url = BASE_URL + href if href.startswith("/") else href

                # Filter to only album review URLs
                if "reviews/albums" not in full_url or full_url in seen:
                    continue
                seen.add(full_url)

                # Walk up DOM for metadata
                card = a_tag.find_parent(
                    lambda t: t.name in ("div", "article", "li")
                    and any(
                        c in " ".join(t.get("class", []))
                        for c in ("review", "Review", "card", "Card", "item", "Item")
                    )
                ) or a_tag.parent

                title_tag = card.select_one("h2, h3, h4, [class*='title'], [class*='Title']")
                artist_tag = card.select_one("[class*='artist'], [class*='Artist']")
                score_tag = card.select_one("[class*='rating'], [class*='Rating'], [class*='score']")
                date_tag = card.select_one("time")

                title = title_tag.get_text(strip=True) if title_tag else a_tag.get_text(strip=True) or "Untitled"
                artist = artist_tag.get_text(strip=True) if artist_tag else ""
                score = score_tag.get_text(strip=True) if score_tag else ""
                pub_date = date_tag.get("datetime", "") if date_tag else ""

                reviews.append({
                    "title": f"{artist} – {title}" if artist else title,
                    "link": full_url,
                    "description": f"Score: {score}" if score else "",
                    "pubDate": pub_date,
                    "author": "Pitchfork",
                })

        browser.close()

    print(f"  Found {len(reviews)} reviews.")
    return reviews


def parse_review_item(item):
    """Extract fields from a Pitchfork GraphQL review item dict."""
    if not isinstance(item, dict):
        return None

    title = item.get("seoTitle") or item.get("title") or ""

    artists = item.get("artists") or item.get("artistNames") or []
    if isinstance(artists, list):
        artist_str = ", ".join(
            a.get("displayName", a.get("name", "")) if isinstance(a, dict) else str(a)
            for a in artists
        )
    else:
        artist_str = str(artists)

    full_title = f"{artist_str} – {title}" if artist_str else title

    url = item.get("url") or item.get("slug") or ""
    if url and not url.startswith("http"):
        url = BASE_URL + url

    rating = item.get("rating") or {}
    score = rating.get("rating") if isinstance(rating, dict) else ""
    descriptor = rating.get("ratingDescriptor", "") if isinstance(rating, dict) else ""

    pub_date = item.get("publishDate") or item.get("pubDate") or ""

    authors = item.get("authors") or item.get("contributors") or []
    if isinstance(authors, list):
        author_str = ", ".join(
            a.get("name", "") if isinstance(a, dict) else str(a)
            for a in authors
        )
    else:
        author_str = ""

    description_parts = []
    if score:
        description_parts.append(f"Score: {score}/10")
    if descriptor:
        description_parts.append(descriptor)
    dek = item.get("dek") or item.get("subhed") or ""
    if dek:
        description_parts.append(dek)
    description = " | ".join(description_parts)

    if not url:
        return None

    return {
        "title": full_title or "Untitled Review",
        "link": url,
        "description": description,
        "pubDate": pub_date,
        "author": author_str or "Pitchfork",
    }


def build_rss(reviews):
    """Build an RSS 2.0 XML tree from the list of review dicts."""
    rss = Element("rss", version="2.0")
    rss.set("xmlns:atom", "http://www.w3.org/2005/Atom")

    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = "Pitchfork – Experimental Reviews"
    SubElement(channel, "link").text = FEED_URL
    SubElement(channel, "description").text = "Latest experimental music reviews from Pitchfork."
    SubElement(channel, "language").text = "en-us"
    SubElement(channel, "lastBuildDate").text = (
        datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    )

    atom_link = SubElement(channel, "atom:link")
    atom_link.set("href", FEED_URL)
    atom_link.set("rel", "self")
    atom_link.set("type", "application/rss+xml")

    for review in reviews:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = review.get("title", "")
        SubElement(item, "link").text = review.get("link", "")
        SubElement(item, "description").text = review.get("description", "")
        SubElement(item, "author").text = review.get("author", "Pitchfork")
        SubElement(item, "guid", isPermaLink="true").text = review.get("link", "")

        pub = review.get("pubDate", "")
        if pub:
            try:
                dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                pub = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
            except ValueError:
                pass
            SubElement(item, "pubDate").text = pub

    return rss


def write_feed(rss_element, output_path=OUTPUT_FILE):
    """Serialize the RSS element to a pretty-printed XML file."""
    raw = tostring(rss_element, encoding="unicode", xml_declaration=False)
    pretty = xml.dom.minidom.parseString(
        '<?xml version="1.0" encoding="UTF-8"?>' + raw
    ).toprettyxml(indent="  ", encoding=None)
    lines = pretty.split("\n")
    if lines[0].startswith("<?xml"):
        lines = lines[1:]
    final = '<?xml version="1.0" encoding="UTF-8"?>\n' + "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final)
    print(f"RSS feed written to: {output_path}")


if __name__ == "__main__":
    reviews = fetch_reviews()
    if not reviews:
        print("No reviews found. The page structure may have changed.", file=sys.stderr)
        sys.exit(1)
    rss = build_rss(reviews)
    write_feed(rss)
