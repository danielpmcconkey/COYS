#!/usr/bin/env python3
"""Catalog refresh for Marcus v2.

Consolidates the maintenance steps from run_daily.py into a standalone script
that Marcus calls on first request of the evening. Designed to complete in
<60 seconds for ~200 channels.

Steps:
  1. Sync subscriptions (optional)
  2. Check RSS feeds for new uploads (parallel, free)
  3. Deduplicate against existing videos
  4. Enrich new videos with metadata (batched YouTube API)
  5. Insert new videos into DB
  6. Expire videos older than 90 days
  7. Output JSON summary

Usage:
    python3 refresh_catalog.py                # Standard refresh
    python3 refresh_catalog.py --sync-subs    # Sync subscriptions first
"""

import argparse
import json
import sys

from auth import get_youtube_service
import db
import metadata
import rss_check
import subscriptions


def refresh(sync_subs=False):
    """Run the catalog refresh pipeline. Returns summary dict."""
    youtube = get_youtube_service()

    sub_result = None
    if sync_subs:
        print("Syncing subscriptions...", file=sys.stderr)
        subs = subscriptions.fetch_subscriptions(youtube)
        sub_result = subscriptions.sync_subscriptions(subs)
        print(f"Sub sync: {json.dumps(sub_result)}", file=sys.stderr)

    channels = db.get_active_channels()
    if not channels:
        return {"channels_checked": 0, "new_videos": 0, "expired": 0,
                "shorts_filtered": 0}

    print(f"Checking {len(channels)} channels...", file=sys.stderr)

    rss_videos = rss_check.check_feeds(channels)
    new_video_count = 0
    shorts_filtered = 0

    if rss_videos:
        candidate_ids = [v["video_id"] for v in rss_videos]
        existing_ids = db.get_existing_video_ids(candidate_ids)
        new_rss = [v for v in rss_videos if v["video_id"] not in existing_ids]

        if new_rss:
            new_video_ids = [v["video_id"] for v in new_rss]
            enriched = metadata.enrich_videos(youtube, new_video_ids)
            shorts_filtered = len(new_video_ids) - len(enriched)

            rss_by_id = {v["video_id"]: v for v in new_rss}
            merged = []
            for ev in enriched:
                vid = ev["video_id"]
                rss_data = rss_by_id.get(vid, {})
                merged.append({
                    "video_id": vid,
                    "channel_id": rss_data.get("channel_id") or ev.get("channel_id"),
                    "title": ev.get("title") or rss_data.get("title", ""),
                    "description": ev.get("description"),
                    "published_at": rss_data.get("published_at"),
                    "duration_seconds": ev.get("duration_seconds"),
                    "thumbnail_url": ev.get("thumbnail_url"),
                    "status": "new",
                })

            new_video_count = db.upsert_videos(merged)

    expired = db.expire_stale_videos(max_age_days=90)

    result = {
        "channels_checked": len(channels),
        "new_videos": new_video_count,
        "shorts_filtered": shorts_filtered,
        "expired": len(expired),
    }

    if sub_result:
        result["subscription_sync"] = sub_result

    return result


def main():
    parser = argparse.ArgumentParser(description="Marcus catalog refresh")
    parser.add_argument("--sync-subs", action="store_true",
                        help="Sync YouTube subscriptions before refresh")
    args = parser.parse_args()

    try:
        result = refresh(sync_subs=args.sync_subs)
        print(json.dumps(result, indent=2, default=str))
    except Exception as e:
        print(json.dumps({"error": str(e)}, indent=2))
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
