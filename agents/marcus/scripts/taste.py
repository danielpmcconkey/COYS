#!/usr/bin/env python3
"""Taste aggregation for Marcus v2.

Computes per-channel quality scores from watch-sync completion data.
Upserts results into marcus.channel_stats.

Quality score formula:
  score = (avg_completion * 0.7) + (watch_ratio * 0.3)
  where watch_ratio = watch_count / (watch_count + skip_count)

Channels with no watch data get no stats row (not a zero score).

Usage:
    python3 taste.py           # Compute and upsert all stats, print summary
    python3 taste.py --dry-run # Compute and print without writing to DB
"""

import argparse
import json
import sys

import db


def compute_stats():
    """Compute quality scores from watch/skip data. Returns list of stat dicts."""
    rows = db.get_watch_data_for_stats()
    stats = []

    for row in rows:
        watch = row["watch_count"] or 0
        skip = row["skip_count"] or 0
        total = watch + skip

        if total == 0:
            continue

        avg_completion = float(row["avg_completion"]) if row["avg_completion"] else None
        watch_ratio = watch / total

        if avg_completion is not None:
            quality_score = (avg_completion * 0.7) + (watch_ratio * 0.3)
        else:
            quality_score = watch_ratio * 0.3

        stats.append({
            "channel_id": row["channel_id"],
            "avg_completion": avg_completion,
            "watch_count": watch,
            "skip_count": skip,
            "quality_score": round(quality_score, 4),
        })

    return stats


def update_all(dry_run=False):
    """Compute and upsert all channel stats. Returns summary."""
    stats = compute_stats()

    if not dry_run:
        for s in stats:
            db.upsert_channel_stats(
                s["channel_id"], s["avg_completion"],
                s["watch_count"], s["skip_count"], s["quality_score"],
            )

    return {
        "channels_scored": len(stats),
        "dry_run": dry_run,
        "stats": stats,
    }


def main():
    parser = argparse.ArgumentParser(description="Marcus taste aggregation")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute and print without writing to DB")
    args = parser.parse_args()

    result = update_all(dry_run=args.dry_run)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
