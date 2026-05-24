#!/media/dan/fdrive/codeprojects/COYS/agents/marcus/scripts/.venv/bin/python3
"""Marcus watch-sync — Shield → DB completion poller.

Detects which Marcus-queued video Dan watched to completion on the NVIDIA
Shield (SmartTube, no Google account) and flips it to `watched` in the Marcus
DB, so the daily playlist stops re-queuing it and the taste loop gets real
signal.

Mechanism (host-side, LAN-only, no root, no login):
  adb connect <shield>  →  adb shell dumpsys media_session
SmartTube publishes a MediaSession exposing the now-playing title + channel +
playback position. We match the title (+channel) against currently-`queued`
rows and mark `watched` when playback parks near the end.

Design notes baked in from live capture on the device (2026-05-24):
  - During active playback (state=3, speed=1.0) `position` is a STALE snapshot
    taken at `updated`; it does not advance live. So we never trust position
    while playing — we only act when playback is STOPPED or PAUSED, where
    speed=0.0 and `position` is an accurate static value.
  - A video that runs to its end in "pause after each video" mode parks at
    state=1 (STOPPED) with position == full duration — NOT state=2. So the
    completion gate is "not playing" (state in {1,2}), not "paused".
  - The metadata description is "<TITLE>, <CHANNEL>, <icon|null>". Titles
    contain commas, so we rsplit from the right.

Only ever sets `watched`. Never infers `skipped`. Never touches anything else.
Privacy invariant: nothing about Dan's viewing leaves the LAN.
"""

import argparse
import logging
import re
import subprocess
import sys
import time
from pathlib import Path

# db.py lives next to this script; make it importable however we're launched.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402  (Marcus's module — we use connect() + update_video_status())

# ── Tunables (overridable via CLI) ──────────────────────────────────────
SHIELD_ENDPOINT = "192.168.50.41:5555"
POLL_INTERVAL_S = 30
WATCHED_THRESHOLD = 0.85
ADB_TIMEOUT_S = 15
SMARTTUBE_PKG = "org.smarttube.stable"

# Dedicated adb server port for the marcus user. adb auth is per-server: the
# server signs the device challenge with its owner's ~/.android/adbkey. Pinning
# our own port guarantees we always use marcus's authorized key and never
# collide with (or get auth-confused by) an interactive adb server dan may be
# running on the default 5037.
ADB_SERVER_PORT = 5038

# PlaybackState codes: 1=stopped, 2=paused, 3=playing, 6=buffering.
# Position is only trustworthy when not playing (speed=0.0).
NOT_PLAYING_STATES = {1, 2}

logger = logging.getLogger("marcus-watch")

_STATE_RE = re.compile(r"\bstate=(\d+)")
_POSITION_RE = re.compile(r"\bposition=(-?\d+)")


# ── ADB / dumpsys ───────────────────────────────────────────────────────

def _adb(*args, timeout=ADB_TIMEOUT_S):
    """Run an adb command, returning CompletedProcess. Never raises on
    nonzero exit — adb's normal failure modes (offline, unauthorized,
    connection refused) are expected when the Shield sleeps."""
    return subprocess.run(
        ["adb", "-P", str(ADB_SERVER_PORT), *args],
        capture_output=True, text=True, timeout=timeout,
    )


def read_smarttube_session():
    """Return dict(state=int, position_ms=int, title=str, channel=str) for the
    current SmartTube MediaSession, or None if nothing is playing / the Shield
    is unreachable."""
    # Idempotent: "already connected" if up, re-establishes after Shield sleep.
    _adb("connect", SHIELD_ENDPOINT)

    try:
        proc = _adb("-s", SHIELD_ENDPOINT, "shell", "dumpsys", "media_session")
    except subprocess.TimeoutExpired:
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None

    return _parse_session(proc.stdout)


def _parse_session(dump):
    """Parse dumpsys media_session output for the SmartTube session block."""
    in_smarttube = False
    state = position_ms = title = channel = None

    for line in dump.splitlines():
        # Session blocks are delimited by `package=<pkg>` lines. The audio
        # summary uses `packages=` (plural) — won't match `package=`.
        if "package=" in line:
            in_smarttube = f"package={SMARTTUBE_PKG}" in line
            continue
        if not in_smarttube:
            continue

        if "state=PlaybackState" in line:
            m_state = _STATE_RE.search(line)
            m_pos = _POSITION_RE.search(line)
            if m_state:
                state = int(m_state.group(1))
            if m_pos:
                position_ms = int(m_pos.group(1))
        elif line.lstrip().startswith("metadata:") and "description=" in line:
            desc = line.split("description=", 1)[1].strip()
            # "<TITLE>, <CHANNEL>, <icon|null>" — title may contain commas.
            parts = desc.rsplit(", ", 2)
            if len(parts) == 3:
                title, channel, _icon = parts
            elif len(parts) == 2:
                title, channel = parts
            else:
                title = desc

    if state is None or title is None:
        return None
    return {"state": state, "position_ms": position_ms, "title": title,
            "channel": channel}


# ── Matching ────────────────────────────────────────────────────────────

def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip()).casefold()


def fetch_queued():
    """Currently-queued videos with the fields we match on."""
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT v.video_id, v.title, v.duration_seconds, c.channel_name
                FROM marcus.video v
                JOIN marcus.channel c ON v.channel_id = c.channel_id
                WHERE v.status = 'queued'
            """)
            return [
                {"video_id": r[0], "title": r[1],
                 "duration_seconds": r[2], "channel_name": r[3]}
                for r in cur.fetchall()
            ]


def match_video(session, queued):
    """Find the queued row matching the now-playing title (+channel).

    Tiered: exact normalized title, then containment (SmartTube sometimes
    appends " | Channel" to the title). Channel disambiguates ties. Returns
    the matched row, or None if no match or ambiguous (we never guess)."""
    st_title = _norm(session["title"])
    st_channel = _norm(session["channel"])

    exact = [v for v in queued if _norm(v["title"]) == st_title]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        exact = [v for v in exact if _norm(v["channel_name"]) == st_channel]
        return exact[0] if len(exact) == 1 else None

    # Containment fallback (e.g. DB title vs "DB title | BBC News").
    contains = [
        v for v in queued
        if st_title and (
            st_title.startswith(_norm(v["title"]))
            or _norm(v["title"]).startswith(st_title)
        )
    ]
    if len(contains) > 1:
        contains = [v for v in contains
                    if _norm(v["channel_name"]) == st_channel]
    return contains[0] if len(contains) == 1 else None


def is_complete(session, video):
    """True if playback is parked near the end of a known-duration video."""
    if session["state"] not in NOT_PLAYING_STATES:
        return False  # position is unreliable while playing
    duration = video["duration_seconds"]
    if not duration or session["position_ms"] is None:
        return False  # no duration → can't compute %; leave for manual handling
    return (session["position_ms"] / 1000.0) / duration >= WATCHED_THRESHOLD


# ── Poll loop ───────────────────────────────────────────────────────────

def poll_once(fired, dry_run=False):
    """One detection cycle. `fired` is the in-session de-dupe set."""
    session = read_smarttube_session()
    if session is None:
        return False  # idle or Shield unreachable

    queued = fetch_queued()
    video = match_video(session, queued)
    if video is None:
        logger.debug("Playing %r (%s) — no queued match",
                     session["title"], session["channel"])
        return False

    vid = video["video_id"]
    if vid in fired:
        return False
    if not is_complete(session, video):
        return False

    pct = (session["position_ms"] / 1000.0) / video["duration_seconds"]
    logger.info("WATCHED %s — %r (%.0f%% of %ss, state=%d)%s",
                vid, video["title"], pct * 100, video["duration_seconds"],
                session["state"], " [dry-run]" if dry_run else "")
    if not dry_run:
        db.update_video_status(vid, "watched")
    fired.add(vid)
    return True


def run_forever(interval, dry_run=False):
    logger.info("marcus-watch starting — shield=%s interval=%ds threshold=%.0f%%",
                SHIELD_ENDPOINT, interval, WATCHED_THRESHOLD * 100)
    fired = set()
    available = None  # track availability to log transitions, not every cycle
    while True:
        try:
            session = read_smarttube_session()
            now_available = session is not None
            if now_available != available:
                logger.info("Shield %s", "available" if now_available else "idle/unreachable")
                available = now_available
            if session is not None:
                queued = fetch_queued()
                video = match_video(session, queued)
                if video and video["video_id"] not in fired and is_complete(session, video):
                    pct = (session["position_ms"] / 1000.0) / video["duration_seconds"]
                    logger.info("WATCHED %s — %r (%.0f%%)%s",
                                video["video_id"], video["title"], pct * 100,
                                " [dry-run]" if dry_run else "")
                    if not dry_run:
                        db.update_video_status(video["video_id"], "watched")
                    fired.add(video["video_id"])
        except Exception:
            logger.exception("poll cycle failed — continuing")
        time.sleep(interval)


# ── CLI ─────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Marcus watch-sync poller")
    p.add_argument("--once", action="store_true",
                   help="Run a single cycle and exit (for testing)")
    p.add_argument("--probe", action="store_true",
                   help="Print the current parsed SmartTube session and exit")
    p.add_argument("--dry-run", action="store_true",
                   help="Detect and log, but do not write to the DB")
    p.add_argument("--interval", type=int, default=POLL_INTERVAL_S,
                   help=f"Poll interval seconds (default {POLL_INTERVAL_S})")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    if args.probe:
        session = read_smarttube_session()
        if session is None:
            print("No SmartTube session (idle or Shield unreachable).")
        else:
            print(f"state={session['state']} position_ms={session['position_ms']}")
            print(f"title={session['title']!r}")
            print(f"channel={session['channel']!r}")
            queued = fetch_queued()
            match = match_video(session, queued)
            print(f"match={match['video_id'] if match else None}"
                  f" ({len(queued)} queued)")
            if match:
                print(f"complete={is_complete(session, match)}")
        return

    if args.once:
        fired = set()
        hit = poll_once(fired, dry_run=args.dry_run)
        print("watched 1 video" if hit else "no completion detected")
        return

    run_forever(args.interval, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
