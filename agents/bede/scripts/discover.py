#!/usr/bin/env python3
"""Discover new transcripts that haven't been summarized yet.

Scans both Hobson and BD transcript directories, compares against the
registry, and outputs JSON listing new candidates and skipped sessions.
"""

import argparse
import glob
import json
import os
import time

TRANSCRIPT_SOURCES = {
    "hobson": "/home/dan/penthouse-pete/.transcripts/",
    "bd": "/media/dan/fdrive/ai-sandbox/workspace/.transcripts/",
}

REGISTRY_PATH = (
    "/media/dan/fdrive/codeprojects/ai-dev-playbook"
    "/TranscriptSummaries/registry.json"
)

ACTIVE_THRESHOLD_MINUTES = 30


def load_registry():
    try:
        with open(REGISTRY_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def extract_session_id(filename):
    """Extract session ID from transcript filename.

    Format: {date}T{time}-{TZ}_{session-id}.md
    Example: 2026-03-04T12-44-EST_56004248-1def-4e5d-bd71-8ad7ac6b2228.md
    """
    base = os.path.splitext(os.path.basename(filename))[0]
    parts = base.split("_", 1)
    if len(parts) == 2:
        return parts[1]
    return None


def extract_timestamp(filename):
    """Extract ISO-ish timestamp from transcript filename.

    Converts the filename prefix to something closer to ISO 8601.
    """
    base = os.path.splitext(os.path.basename(filename))[0]
    prefix = base.split("_", 1)[0]
    # prefix like: 2026-03-04T12-44-EST
    # Best effort — return as-is for the registry
    return prefix


def is_possibly_active(filepath):
    """Check if a transcript might still be in progress."""
    mtime = os.path.getmtime(filepath)
    age_minutes = (time.time() - mtime) / 60
    return age_minutes < ACTIVE_THRESHOLD_MINUTES


def discover(limit=None):
    registry = load_registry()
    # Build lookup of known IDs — registry may have full UUIDs while filenames
    # only contain the first 8 chars, so index by both full and short forms
    known_ids = set()
    for entry in registry:
        known_ids.add(entry["session_id"])
        known_ids.add(entry.get("session_id_short", entry["session_id"][:8]))

    new_transcripts = []
    skipped = []

    for source, directory in TRANSCRIPT_SOURCES.items():
        if not os.path.isdir(directory):
            skipped.append({
                "source": source,
                "reason": f"directory not found: {directory}",
            })
            continue

        pattern = os.path.join(directory, "*.md")
        for filepath in sorted(glob.glob(pattern)):
            filename = os.path.basename(filepath)

            # Skip debug logs
            if filename.startswith("_debug_"):
                continue

            session_id = extract_session_id(filename)
            if not session_id:
                continue

            # Already processed
            if session_id in known_ids:
                continue

            # Possibly still active
            if is_possibly_active(filepath):
                skipped.append({
                    "file": filename,
                    "path": filepath,
                    "source": source,
                    "session_id": session_id,
                    "reason": "possibly active",
                })
                continue

            new_transcripts.append({
                "file": filename,
                "path": filepath,
                "source": source,
                "session_id": session_id,
                "session_id_short": session_id[:8],
                "timestamp": extract_timestamp(filename),
            })

    output = {
        "new": new_transcripts[:limit] if limit else new_transcripts,
        "skipped": skipped,
        "registry_count": len(registry),
        "total_new": len(new_transcripts),
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit", type=int, default=5,
        help="Max transcripts to return per run (0 = unlimited, default 5)",
    )
    args = parser.parse_args()
    discover(limit=args.limit or None)
