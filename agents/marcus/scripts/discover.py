#!/usr/bin/env python3
"""Content discovery for Marcus v2.

Finds new channels and videos outside Dan's subscriptions using YouTube
Search API. Discovered videos are inserted with discovered=true.

Discovery strategy:
  1. Load top-performing channels (highest quality scores)
  2. Extract categories/topics from those channels
  3. Run 2-3 targeted searches based on those topics
  4. Filter: exclude known channels (subscribed or blacklisted), Shorts
  5. Enrich metadata for discovered videos
  6. Insert into DB with discovered=true

Quota budget: 100 units per search.list call. 2-3 calls per session = 200-300 units.

Usage:
    python3 discover.py                    # Run discovery pass
    python3 discover.py --dry-run          # Search and print without inserting
    python3 discover.py --queries "topic1" "topic2"  # Override search queries
"""

import argparse
import json
import sys

from auth import get_youtube_service
import db
import metadata


DEFAULT_QUERY_COUNT = 3


def build_search_queries(top_channels):
    """Generate search queries from top-performing channel categories."""
    categories = {}
    for ch in top_channels:
        cat = ch.get("category")
        if cat:
            categories[cat] = categories.get(cat, 0) + 1

    sorted_cats = sorted(categories.items(), key=lambda x: -x[1])
    queries = [cat for cat, _ in sorted_cats[:DEFAULT_QUERY_COUNT]]

    if not queries:
        queries = ["documentary", "explainer", "history"]

    return queries


def search_videos(youtube, query, max_results=10):
    """Run a YouTube search and return raw results."""
    try:
        response = youtube.search().list(
            part="snippet",
            q=query,
            type="video",
            videoDuration="medium",
            relevanceLanguage="en",
            maxResults=max_results,
            order="relevance",
        ).execute()
    except Exception as e:
        print(f"Search failed for '{query}': {e}", file=sys.stderr)
        return []

    results = []
    for item in response.get("items", []):
        snippet = item["snippet"]
        results.append({
            "video_id": item["id"]["videoId"],
            "channel_id": snippet["channelId"],
            "channel_name": snippet.get("channelTitle", ""),
            "title": snippet.get("title", ""),
        })

    return results


def run_discovery(youtube, queries=None, dry_run=False):
    """Execute the discovery pipeline. Returns summary dict."""
    stats = db.get_channel_stats()
    top_channels = stats[:10] if stats else []

    if not queries:
        queries = build_search_queries(top_channels)

    print(f"Discovery queries: {queries}", file=sys.stderr)

    known_channels = {ch["channel_id"] for ch in db.get_active_channels()}
    blacklisted = {ch["channel_id"] for ch in db.get_blacklisted_channels()}
    exclude = known_channels | blacklisted

    all_found = []
    seen_videos = set()
    seen_channels = set()

    for query in queries:
        results = search_videos(youtube, query)
        for r in results:
            if r["channel_id"] in exclude:
                continue
            if r["video_id"] in seen_videos:
                continue
            if r["channel_id"] in seen_channels:
                continue
            seen_videos.add(r["video_id"])
            seen_channels.add(r["channel_id"])
            all_found.append(r)

    if not all_found:
        return {"queries": queries, "discovered": 0, "inserted": 0}

    existing = db.get_existing_video_ids([v["video_id"] for v in all_found])
    new_found = [v for v in all_found if v["video_id"] not in existing]

    if not new_found:
        return {"queries": queries, "discovered": len(all_found),
                "already_known": len(all_found), "inserted": 0}

    video_ids = [v["video_id"] for v in new_found]
    enriched = metadata.enrich_videos(youtube, video_ids)

    found_by_id = {v["video_id"]: v for v in new_found}
    to_insert = []
    for ev in enriched:
        vid = ev["video_id"]
        source = found_by_id.get(vid, {})
        to_insert.append({
            "video_id": vid,
            "channel_id": source.get("channel_id") or ev.get("channel_id"),
            "title": ev.get("title") or source.get("title", ""),
            "description": ev.get("description"),
            "published_at": None,
            "duration_seconds": ev.get("duration_seconds"),
            "thumbnail_url": ev.get("thumbnail_url"),
            "status": "new",
        })

    inserted = 0
    if not dry_run and to_insert:
        inserted = db.upsert_videos(to_insert)
        # Mark as discovered
        with db.connect() as conn:
            with conn.cursor() as cur:
                for v in to_insert:
                    cur.execute(
                        "UPDATE marcus.video SET discovered = TRUE WHERE video_id = %s",
                        (v["video_id"],))
            conn.commit()

    return {
        "queries": queries,
        "search_results": len(all_found),
        "new_videos": len(new_found),
        "enriched": len(enriched),
        "inserted": inserted,
        "dry_run": dry_run,
        "videos": [{"video_id": v["video_id"], "title": v["title"],
                     "channel": found_by_id.get(v["video_id"], {}).get("channel_name", "")}
                    for v in to_insert],
    }


def main():
    parser = argparse.ArgumentParser(description="Marcus content discovery")
    parser.add_argument("--dry-run", action="store_true",
                        help="Search and print without inserting into DB")
    parser.add_argument("--queries", nargs="*",
                        help="Override search queries")
    args = parser.parse_args()

    youtube = get_youtube_service()
    result = run_discovery(youtube, queries=args.queries, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
