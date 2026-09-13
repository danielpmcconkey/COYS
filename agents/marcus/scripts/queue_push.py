#!/usr/bin/env python3
"""Push the Marcus Queue playlist to SmartTube on the Shield via ADB.

Sends an intent with the playlist URL. SmartTube opens it natively with a
browsable queue and auto-advance. Also records the queue in marcus.queue
for tracking.

Usage:
    python3 queue_push.py VIDEO_ID1 VIDEO_ID2 ...
    echo '{"video_ids": ["abc","def"]}' | python3 queue_push.py
"""

import argparse
import json
import subprocess
import sys

import db


def verify_playlist(playlist_id, video_ids):
    """Check the live playlist actually holds video_ids.

    queue_push sends a playlist URL, not the videos themselves — so if
    build_playlist.py hasn't run, the Shield plays a stale lineup while the
    DB records the new one. Returns (ok, detail_dict).
    """
    from auth import get_youtube_service
    import playlist as playlist_mod

    youtube = get_youtube_service()
    live = [i["video_id"] for i in playlist_mod.list_playlist(youtube, playlist_id)]

    wanted, actual = set(video_ids), set(live)
    missing, unexpected = wanted - actual, actual - wanted

    return not (missing or unexpected), {
        "playlist_count": len(live),
        "requested_count": len(video_ids),
        "missing_from_playlist": sorted(missing),
        "unexpected_in_playlist": sorted(unexpected),
        "order_matches": live == list(video_ids),
    }

SHIELDS = {
    "downstairs": "192.168.50.41:5555",
    "upstairs": "192.168.50.42:5555",
}
DEFAULT_SHIELD = "downstairs"
ADB_SERVER_PORT = 5038
ADB_TIMEOUT_S = 15
SMARTTUBE_PKG = "org.smarttube.stable"


def _adb(*args, timeout=ADB_TIMEOUT_S):
    """Run an adb command. Returns CompletedProcess."""
    return subprocess.run(
        ["adb", "-P", str(ADB_SERVER_PORT), *args],
        capture_output=True, text=True, timeout=timeout,
    )


def push_playlist(playlist_id, video_ids, shield=DEFAULT_SHIELD):
    """Push playlist URL to SmartTube and record the queue in DB.

    Returns result dict.
    """
    endpoint = SHIELDS[shield]
    _adb("connect", endpoint)

    url = f"https://www.youtube.com/playlist?list={playlist_id}"
    proc = _adb(
        "-s", endpoint, "shell",
        "am", "start", "-a", "android.intent.action.VIEW",
        "-d", url,
        "-n", f"{SMARTTUBE_PKG}/com.liskovsoft.smartyoutubetv2.tv.ui.main.SplashActivity",
    )

    adb_ok = proc.returncode == 0

    if video_ids:
        db.insert_queue(video_ids)

    return {
        "adb_success": adb_ok,
        "shield": shield,
        "playlist_url": url,
        "videos_queued": len(video_ids),
        "adb_stdout": proc.stdout.strip() if proc.stdout else "",
        "adb_stderr": proc.stderr.strip() if proc.stderr else "",
    }


def main():
    parser = argparse.ArgumentParser(description="Push Marcus playlist to Shield")
    parser.add_argument("video_ids", nargs="*", help="Video IDs in queue order")
    parser.add_argument("--playlist-id", help="YouTube playlist ID (reads from DB if omitted)")
    parser.add_argument("--shield", choices=list(SHIELDS), default=DEFAULT_SHIELD,
                        help=f"Target Shield (default: {DEFAULT_SHIELD})")
    parser.add_argument("--skip-verify", action="store_true",
                        help="Push without checking the playlist matches (not advised)")
    args = parser.parse_args()

    video_ids = args.video_ids
    if not video_ids and not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
        if raw:
            data = json.loads(raw)
            video_ids = data.get("video_ids", [])

    playlist_id = args.playlist_id or db.get_playlist_config()
    if not playlist_id:
        print(json.dumps({"error": "No playlist ID found. Run build_playlist.py first."}))
        sys.exit(1)

    # Refuse to push a playlist that doesn't hold the videos we're recording.
    if video_ids and not args.skip_verify:
        ok, detail = verify_playlist(playlist_id, video_ids)
        if not ok:
            print(json.dumps({
                "error": "Playlist does not match the videos being queued. "
                         "Run build_playlist.py before queue_push.py — "
                         "nothing was pushed and nothing was recorded.",
                **detail,
            }, indent=2))
            sys.exit(1)

    result = push_playlist(playlist_id, video_ids, shield=args.shield)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
