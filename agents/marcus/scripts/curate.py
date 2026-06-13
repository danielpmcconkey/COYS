#!/usr/bin/env python3
"""Fetch curation candidates for Marcus v2.

Queries the catalog for videos the model can curate from. Returns structured
JSON with taste signals and metadata. The model (Opus) does the actual
selection — this script provides the data.

Usage:
    python3 curate.py                          # All candidates
    python3 curate.py --max-duration 900       # <=15 min only
    python3 curate.py --language spanish        # Tier 4 only
    python3 curate.py --exclude-channels UC... UC...  # Skip specific channels
"""

import argparse
import json
import sys

import db


def get_candidates(max_duration=None, language=None, exclude_channels=None,
                   max_age_days=90):
    """Fetch candidates and attach recently-queued flags."""
    candidates = db.get_curation_candidates(
        max_duration=max_duration,
        language=language,
        exclude_channels=exclude_channels,
        max_age_days=max_age_days,
    )

    recently_queued = db.get_recently_queued_video_ids(days=7)

    out = []
    for c in candidates:
        row = dict(c)
        row["recently_queued"] = row["video_id"] in recently_queued
        out.append(row)

    return out


def main():
    parser = argparse.ArgumentParser(description="Marcus curation candidates")
    parser.add_argument("--max-duration", type=int,
                        help="Maximum duration in seconds")
    parser.add_argument("--language", choices=["spanish"],
                        help="Filter by language tier")
    parser.add_argument("--exclude-channels", nargs="*", default=None,
                        help="Channel IDs to exclude")
    parser.add_argument("--max-age-days", type=int, default=90,
                        help="Maximum video age in days (default 90)")
    args = parser.parse_args()

    candidates = get_candidates(
        max_duration=args.max_duration,
        language=args.language,
        exclude_channels=args.exclude_channels,
        max_age_days=args.max_age_days,
    )

    print(json.dumps({
        "candidate_count": len(candidates),
        "candidates": candidates,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
