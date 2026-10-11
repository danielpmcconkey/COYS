#!/home/dan/.openclaw/skills/morning-report/scripts/.venv/bin/python3
"""Fetch RSS feeds and output recent entries as JSON."""

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import feedparser

USER_AGENT = "zazu-morning-report/1.0 (by /u/danielpmcconkey)"


def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()

# Reddit allows one anonymous request per ~60s per IP, so all subreddits go in
# a single multireddit request. top?t=day ranks by engagement, not recency.
FEEDS = {
    "Reddit": "https://www.reddit.com/r/askhistorians+askscience+charlottefootballclub+coys+futurology+metroidvania+programming+science+tech+worldnews+LocalLLaMA+MachineLearning+artificial+singularity+ClaudeAI/top.rss?t=day&limit=100",
    "Hacker News": "https://hnrss.org/frontpage",
    "MarketWatch": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "NPR": "https://feeds.npr.org/1001/rss.xml",
    "BBC": "http://feeds.bbci.co.uk/news/rss.xml",
}

# Entries kept per feed; the combined Reddit feed spans 15 subreddits.
ENTRY_CAP = {"Reddit": 100}
DEFAULT_ENTRY_CAP = 15


def fetch_feeds(hours=24):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    all_feeds = []

    for source, url in FEEDS.items():
        try:
            try:
                status, body = http_get(url)
            except urllib.error.HTTPError as e:
                all_feeds.append({
                    "source": source,
                    "error": f"HTTP {e.code}",
                    "entries": [],
                })
                continue
            feed = feedparser.parse(body)
            entries = []
            for entry in feed.entries[:ENTRY_CAP.get(source, DEFAULT_ENTRY_CAP)]:
                published = None
                for date_field in ("published_parsed", "updated_parsed"):
                    parsed = getattr(entry, date_field, None)
                    if parsed:
                        published = datetime(*parsed[:6], tzinfo=timezone.utc)
                        break

                if published and published < cutoff:
                    continue

                item = {
                    "title": getattr(entry, "title", "(no title)"),
                    "link": getattr(entry, "link", ""),
                    "summary": getattr(entry, "summary", "")[:300],
                    "published": str(published) if published else "unknown",
                }
                comments = getattr(entry, "comments", None)
                if comments:
                    item["comments"] = comments
                tags = getattr(entry, "tags", None)
                if source == "Reddit" and tags:
                    item["subreddit"] = tags[0].term
                entries.append(item)

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
