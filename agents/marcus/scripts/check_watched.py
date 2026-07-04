#!/usr/bin/env python3
"""Check SmartTube backup caches on both Shields for watched videos.

Reads the auto-backup SharedPreferences file from external storage (no root
needed), parses playback positions, and marks videos as watched in the Marcus
DB when completion >= 85%.

SmartTube updates this file daily (~13:22 upstairs, ~09:58 downstairs).
Run this before curating to reconcile what Dan actually watched.

Usage:
    python3 check_watched.py              # Check both shields, update DB
    python3 check_watched.py --dry-run    # Report without writing
    python3 check_watched.py --shield upstairs  # Check one shield only
"""

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db

SHIELDS = {
    "downstairs": "192.168.50.41:5555",
    "upstairs": "192.168.50.42:5555",
}
ADB_SERVER_PORT = 5038
ADB_TIMEOUT_S = 15
WATCHED_THRESHOLD = 0.85

BACKUP_PATH = (
    "/sdcard/Android/media/org.smarttube.stable/data/org.smarttube.stable"
    "/Backup/shared_prefs/org.smarttube.stable_preferences.xml"
)


def _adb(*args, timeout=ADB_TIMEOUT_S):
    return subprocess.run(
        ["adb", "-P", str(ADB_SERVER_PORT), *args],
        capture_output=True, text=True, timeout=timeout,
    )


def read_backup(endpoint):
    """Pull and parse the SmartTube backup from a Shield.

    Returns list of dicts: {video_id, title, position_ms, duration_ms, pct}
    """
    _adb("connect", endpoint)
    try:
        proc = _adb("-s", endpoint, "shell", "cat", BACKUP_PATH, timeout=30)
    except subprocess.TimeoutExpired:
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None

    try:
        root = ET.fromstring(proc.stdout)
    except ET.ParseError:
        return None

    for el in root:
        if el.get("name") == "state_updater_data":
            return _parse_state_data(unescape(el.text or ""))
    return None


def _parse_state_data(raw):
    """Parse the state_updater_data blob into video entries."""
    entries = raw.split("&si;")
    results = []

    for entry in entries:
        parts = entry.split("&vi;")
        if len(parts) < 4:
            continue
        video_id = parts[3]
        title = parts[2]

        last_field = parts[-1] if parts else ""
        sf_parts = last_field.split("&sf;")
        if len(sf_parts) < 3:
            continue
        try:
            position_ms = int(sf_parts[-3])
            duration_ms = int(sf_parts[-2])
        except ValueError:
            continue

        if duration_ms <= 0:
            continue

        pct = position_ms / duration_ms
        results.append({
            "video_id": video_id,
            "title": title,
            "position_ms": position_ms,
            "duration_ms": duration_ms,
            "pct": pct,
        })

    return results


def reconcile(shields=None, dry_run=False):
    """Read watch data from Shields and mark completed videos in DB.

    Returns summary dict.
    """
    if shields is None:
        shields = list(SHIELDS.keys())

    all_watched = {}
    shield_results = {}

    for name in shields:
        endpoint = SHIELDS.get(name)
        if not endpoint:
            shield_results[name] = {"error": f"Unknown shield: {name}"}
            continue

        entries = read_backup(endpoint)
        if entries is None:
            shield_results[name] = {"error": "Unreachable or no data"}
            continue

        watched = [e for e in entries if e["pct"] >= WATCHED_THRESHOLD]
        shield_results[name] = {
            "entries_total": len(entries),
            "entries_watched": len(watched),
        }

        for e in watched:
            vid = e["video_id"]
            if vid not in all_watched or e["pct"] > all_watched[vid]["pct"]:
                all_watched[vid] = e

    watched_ids = set(all_watched.keys())
    if not watched_ids:
        return {
            "shields": shield_results,
            "newly_marked": 0,
            "already_watched": 0,
            "videos": [],
        }

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

    for vid, entry in all_watched.items():
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
        "shields": shield_results,
        "newly_marked": len(newly_marked),
        "already_watched": already_watched,
        "videos": newly_marked,
    }


def main():
    parser = argparse.ArgumentParser(description="Marcus watch reconciliation")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report without updating the database")
    parser.add_argument("--shield", choices=list(SHIELDS.keys()),
                        help="Check a single shield only")
    args = parser.parse_args()

    shields = [args.shield] if args.shield else None
    result = reconcile(shields=shields, dry_run=args.dry_run)

    if args.dry_run:
        result["dry_run"] = True

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
