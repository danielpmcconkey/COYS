#!/usr/bin/env python3
"""Check FreeTube watch history on the Steam Machine for watched videos.

Reads FreeTube's history.db over SSH, parses playback positions, and marks
videos as watched in the Marcus DB when completion >= 85%.

FreeTube stores history as JSON-lines in:
  ~/.var/app/io.freetubeapp.FreeTube/config/FreeTube/history.db

Each line has: videoId, title, author, authorId, lengthSeconds, watchProgress
(seconds watched), timeWatched (epoch ms).

Usage:
    python3 check_freetube.py              # Check Steam Machine, update DB
    python3 check_freetube.py --dry-run    # Report without writing
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db

STEAM_MACHINE = "deck@192.168.50.225"
HISTORY_PATH = (
    "/home/deck/.var/app/io.freetubeapp.FreeTube/config/FreeTube/history.db"
)
SSH_TIMEOUT_S = 15
WATCHED_THRESHOLD = 0.85


def read_history():
    """Read FreeTube history.db over SSH.

    Returns list of dicts with video_id, title, author, duration_s,
    watch_progress_s, pct. Returns None if unreachable.
    """
    try:
        proc = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
             STEAM_MACHINE, "cat", HISTORY_PATH],
            capture_output=True, text=True, timeout=SSH_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None

    results = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        video_id = entry.get("videoId")
        duration = entry.get("lengthSeconds", 0)
        progress = entry.get("watchProgress", 0)
        if not video_id or not duration:
            continue

        pct = progress / duration
        results.append({
            "video_id": video_id,
            "title": entry.get("title", ""),
            "author": entry.get("author", ""),
            "duration_s": duration,
            "watch_progress_s": progress,
            "pct": pct,
        })

    return results


def reconcile(dry_run=False):
    """Read watch data from FreeTube and mark completed videos in DB."""
    entries = read_history()
    if entries is None:
        return {
            "source": "freetube",
            "host": STEAM_MACHINE,
            "error": "Unreachable or no history data",
            "warnings": [
                "Steam Machine unreachable — FreeTube watch data is MISSING; "
                "videos watched there will be re-queued."
            ],
            "newly_marked": 0,
            "already_watched": 0,
            "videos": [],
        }

    watched = [e for e in entries if e["pct"] >= WATCHED_THRESHOLD]
    watched_ids = {e["video_id"] for e in watched}

    if not watched_ids:
        return {
            "source": "freetube",
            "host": STEAM_MACHINE,
            "entries_total": len(entries),
            "entries_watched": 0,
            "warnings": [],
            "newly_marked": 0,
            "already_watched": 0,
            "videos": [],
        }

    best = {}
    for e in watched:
        vid = e["video_id"]
        if vid not in best or e["pct"] > best[vid]["pct"]:
            best[vid] = e

    conn = db.connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT video_id, status FROM marcus.video
        WHERE video_id = ANY(%s)
    """, (list(watched_ids),))
    db_states = {row[0]: row[1] for row in cur.fetchall()}
    cur.close()
    conn.close()

    newly_marked = []
    already_watched = 0

    for vid, entry in best.items():
        status = db_states.get(vid)
        if status is None:
            continue
        if status == "watched":
            already_watched += 1
            continue
        if status in ("skipped", "expired"):
            continue
        if not dry_run:
            db.set_video_watched(vid, completion_pct=entry["pct"])
        newly_marked.append({
            "video_id": vid,
            "title": entry["title"],
            "pct": round(entry["pct"] * 100),
            "previous_status": status,
        })

    return {
        "source": "freetube",
        "host": STEAM_MACHINE,
        "entries_total": len(entries),
        "entries_watched": len(watched),
        "warnings": [],
        "newly_marked": len(newly_marked),
        "already_watched": already_watched,
        "videos": newly_marked,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Marcus FreeTube watch reconciliation"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Report without updating the database")
    args = parser.parse_args()

    result = reconcile(dry_run=args.dry_run)
    if args.dry_run:
        result["dry_run"] = True

    print(json.dumps(result, indent=2, default=str))

    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
