#!/home/dan/.openclaw/skills/morning-report/scripts/.venv/bin/python3
"""Fetch RSS feeds and output recent entries as JSON."""

import json
import sys
from datetime import datetime, timedelta, timezone

import feedparser

FEEDS = {
    "Reddit": "https://www.reddit.com/r/askhistorians+askscience+charlottefootballclub+coys+futurology+metroidvania+programming+science+tech+worldnews/.rss",
    "Reddit AI/LLM": "https://www.reddit.com/r/LocalLLaMA+MachineLearning+artificial+singularity+ClaudeAI/.rss",
    "Hacker News": "https://hnrss.org/frontpage",
    "Yahoo Finance": "https://finance.yahoo.com/news/rssindex",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "Reuters": "https://feeds.reuters.com/reuters/topNews",
    "BBC": "http://feeds.bbci.co.uk/news/rss.xml",
}


def fetch_feeds(hours=24):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    all_feeds = []

    for source, url in FEEDS.items():
        try:
            feed = feedparser.parse(url)
            entries = []
            for entry in feed.entries[:15]:
                published = None
                for date_field in ("published_parsed", "updated_parsed"):
                    parsed = getattr(entry, date_field, None)
                    if parsed:
                        published = datetime(*parsed[:6], tzinfo=timezone.utc)
                        break

                if published and published < cutoff:
                    continue

                entries.append({
                    "title": getattr(entry, "title", "(no title)"),
                    "link": getattr(entry, "link", ""),
                    "summary": getattr(entry, "summary", "")[:300],
                    "published": str(published) if published else "unknown",
                })

            all_feeds.append({
                "source": source,
                "feed_title": getattr(feed.feed, "title", source),
                "entries": entries,
            })
        except Exception as e:
            all_feeds.append({
                "source": source,
                "error": str(e),
                "entries": [],
            })

    print(json.dumps(all_feeds, indent=2))


if __name__ == "__main__":
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    fetch_feeds(hours)
