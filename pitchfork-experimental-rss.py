#!/usr/bin/env python3
"""
Pitchfork Experimental Reviews RSS Feed Generator
---------------------------------------------------
Scrapes https://pitchfork.com/genre/experimental/review/
and generates a valid RSS 2.0 feed as feed.xml.

Usage:
    pip install requests beautifulsoup4
    python pitchfork_rss.py

To automate, add to cron (e.g. every hour):
    0 * * * * /usr/bin/python3 /path/to/pitchfork_rss.py
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from xml.etree.ElementTree import Element, SubElement, tostring
import xml.dom.minidom
import json
import sys

BASE_URL = "https://pitchfork.com"
FEED_URL = f"{BASE_URL}/genre/experimental/review/"
OUTPUT_FILE = "feed.xml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_reviews():
    """Fetch the Pitchfork experimental reviews page and parse review items."""
    print(f"Fetching {FEED_URL} ...")
    resp = requests.get(FEED_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    reviews = []

    # Pitchfork renders data in a <script id="__NEXT_DATA__"> JSON blob
    next_data_tag = soup.find("script", id="__NEXT_DATA__")
    if next_data_tag:
        try:
            data = json.loads(next_data_tag.string)
            # Navigate the Next.js page props to find review items
            results = (
                data.get("props", {})
                    .get("pageProps", {})
                    .get("urqlState", {})
            )
            # The urqlState is a dict of query results; search for review lists
            for key, val in results.items():
                if not isinstance(val, dict):
                    continue
                content = val.get("data", {})
                if not isinstance(content, dict):
                    continue
                # Try common Pitchfork GraphQL field names
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

    # Fallback: parse HTML directly if JSON approach yielded nothing
    if not reviews:
        print("  Falling back to HTML scraping...")
        # Pitchfork review cards typically use these selectors (may need updating)
        for card in soup.select("div.review, article.review, div[class*='Review']"):
            title_tag = card.select_one("h2, h3, [class*='title']")
            artist_tag = card.select_one("[class*='artist'], [class*='Artist']")
            link_tag = card.select_one("a[href]")
            score_tag = card.select_one("[class*='rating'], [class*='score']")
            date_tag = card.select_one("time")

            title = title_tag.get_text(strip=True) if title_tag else "Untitled"
            artist = artist_tag.get_text(strip=True) if artist_tag else ""
            link = BASE_URL + link_tag["href"] if link_tag and link_tag["href"].startswith("/") else (link_tag["href"] if link_tag else "")
            score = score_tag.get_text(strip=True) if score_tag else ""
            pub_date = date_tag.get("datetime", "") if date_tag else ""

            if link:
                reviews.append({
                    "title": f"{artist} – {title}" if artist else title,
                    "link": link,
                    "description": f"Score: {score}" if score else "",
                    "pubDate": pub_date,
                    "author": "Pitchfork",
                })

    print(f"  Found {len(reviews)} reviews.")
    return reviews


def parse_review_item(item):
    """Extract fields from a Pitchfork GraphQL review item dict."""
    if not isinstance(item, dict):
        return None

    # Title / album name
    title = item.get("seoTitle") or item.get("title") or ""
    # Artist
    artists = item.get("artists") or item.get("artistNames") or []
    if isinstance(artists, list):
        artist_str = ", ".join(
            a.get("displayName", a.get("name", "")) if isinstance(a, dict) else str(a)
            for a in artists
        )
    else:
        artist_str = str(artists)

    full_title = f"{artist_str} – {title}" if artist_str else title

    # URL
    url = item.get("url") or item.get("slug") or ""
    if url and not url.startswith("http"):
        url = BASE_URL + url

    # Score
    rating = item.get("rating") or {}
    score = rating.get("rating") if isinstance(rating, dict) else ""
    descriptor = rating.get("ratingDescriptor", "") if isinstance(rating, dict) else ""

    # Date
    pub_date = item.get("publishDate") or item.get("pubDate") or ""

    # Author
    authors = item.get("authors") or item.get("contributors") or []
    if isinstance(authors, list):
        author_str = ", ".join(
            a.get("name", "") if isinstance(a, dict) else str(a)
            for a in authors
        )
    else:
        author_str = ""

    # Description
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
    SubElement(channel, "description").text = (
        "Latest experimental music reviews from Pitchfork."
    )
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
            # Try to reformat ISO date to RFC 2822 for RSS
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
    # minidom adds its own declaration; strip the duplicate
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
