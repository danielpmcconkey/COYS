#!/usr/bin/env python3
"""Database operations for Marcus. All SQL lives here.

Uses the marcus schema in the openclaw database.
Connection credentials from ~/.pgpass (standard pgpass format: host:port:db:user:password).
"""

import json
import os
import sys

import psycopg2
import psycopg2.extras

PGPASS_FILE = os.path.expanduser("~/.pgpass")


def _read_pgpass():
    """Read connection params from pgpass file."""
    with open(PGPASS_FILE) as f:
        line = f.read().strip()
    host, port, dbname, user, password = line.split(":")
    return dict(host=host, port=int(port), dbname=dbname, user=user, password=password)


def get_connection():
    """Return a new psycopg2 connection."""
    return psycopg2.connect(**_read_pgpass())


# Aliases for convenience
connect = get_connection


# ── Channel operations ──────────────────────────────────────────────

def get_active_channels():
    """Return all subscribed, non-blacklisted channels."""
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT channel_id, channel_name, tier, category, last_upload_at
                FROM marcus.channel
                WHERE subscribed = TRUE AND blacklisted = FALSE
                  AND tier IN (0, 1, 2, 3, 4)
                ORDER BY tier, channel_name
            """)
            return cur.fetchall()


def get_tier1_channels():
    """Return all tier 1 (auto-queue) channels."""
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT channel_id, channel_name, last_upload_at
                FROM marcus.channel
                WHERE subscribed = TRUE AND blacklisted = FALSE AND tier = 1
                ORDER BY channel_name
            """)
            return cur.fetchall()


def upsert_channels(channels):
    """Insert or update channels. channels is a list of {channel_id, channel_name}.

    New channels get tier 2. Existing channels get their name updated.
    Returns (inserted, updated) counts.
    """
    inserted = 0
    updated = 0
    with connect() as conn:
        with conn.cursor() as cur:
            for ch in channels:
                cur.execute("""
                    INSERT INTO marcus.channel (channel_id, channel_name, tier, subscribed)
                    VALUES (%s, %s, 2, TRUE)
                    ON CONFLICT (channel_id) DO UPDATE SET
                        channel_name = EXCLUDED.channel_name,
                        subscribed = TRUE,
                        updated_at = now()
                    RETURNING (xmax = 0) AS is_insert
                """, (ch["channel_id"], ch["channel_name"]))
                row = cur.fetchone()
                if row[0]:
                    inserted += 1
                else:
                    updated += 1
        conn.commit()
    return inserted, updated


def mark_unsubscribed(active_channel_ids):
    """Mark channels not in active_channel_ids as unsubscribed.

    Returns count of channels marked unsubscribed.
    """
    if not active_channel_ids:
        return 0
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE marcus.channel
                SET subscribed = FALSE, updated_at = now()
                WHERE subscribed = TRUE
                  AND tier NOT IN (0, 4)
                  AND channel_id != ALL(%s)
            """, (list(active_channel_ids),))
            count = cur.rowcount
        conn.commit()
    return count


def update_channel_last_upload(channel_id, last_upload_at):
    """Set the last_upload_at timestamp for a channel."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE marcus.channel
                SET last_upload_at = %s, updated_at = now()
                WHERE channel_id = %s
            """, (last_upload_at, channel_id))
        conn.commit()


def set_channel_tier(channel_id, tier):
    """Set a channel's tier (0=news, 1=must-watch, 2=priority, 3=filler, 4=spanish)."""
    if tier not in (0, 1, 2, 3, 4):
        raise ValueError(f"Invalid tier: {tier}")
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE marcus.channel
                SET tier = %s, updated_at = now()
                WHERE channel_id = %s
            """, (tier, channel_id))
        conn.commit()


def find_channels_by_name(name):
    """Return channels whose name matches `name` (case-insensitive substring).

    Lets the agent resolve a fuzzy name from Discord to an exact channel_id
    deterministically, rather than improvising a query."""
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT channel_id, channel_name, tier, subscribed
                FROM marcus.channel
                WHERE channel_name ILIKE %s
                ORDER BY subscribed DESC, channel_name
            """, (f"%{name}%",))
            return cur.fetchall()


# ── Video operations ────────────────────────────────────────────────

def get_existing_video_ids(video_ids):
    """Given a list of video IDs, return the set that already exist in DB."""
    if not video_ids:
        return set()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT video_id FROM marcus.video
                WHERE video_id = ANY(%s)
            """, (list(video_ids),))
            return {row[0] for row in cur.fetchall()}


def upsert_videos(videos):
    """Insert new videos. videos is a list of dicts with keys:
    video_id, channel_id, title, description, published_at,
    duration_seconds, thumbnail_url, status.

    Returns count inserted.
    """
    if not videos:
        return 0
    inserted = 0
    with connect() as conn:
        with conn.cursor() as cur:
            for v in videos:
                cur.execute("""
                    INSERT INTO marcus.video
                        (video_id, channel_id, title, description, published_at,
                         duration_seconds, thumbnail_url, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (video_id) DO NOTHING
                """, (
                    v["video_id"], v["channel_id"], v["title"],
                    v.get("description"), v["published_at"],
                    v.get("duration_seconds"), v.get("thumbnail_url"),
                    v.get("status", "new"),
                ))
                inserted += cur.rowcount
        conn.commit()
    return inserted


def update_video_status(video_id, status, playlist_item_id=None):
    """Update a video's status. Optionally set playlist_item_id and queued_at."""
    with connect() as conn:
        with conn.cursor() as cur:
            if status == "queued":
                cur.execute("""
                    UPDATE marcus.video
                    SET status = %s, playlist_item_id = %s, queued_at = now(),
                        last_queued_at = now(), times_queued = times_queued + 1
                    WHERE video_id = %s
                      AND status NOT IN ('watched', 'skipped')
                """, (status, playlist_item_id, video_id))
            elif status == "expired":
                cur.execute("""
                    UPDATE marcus.video
                    SET status = %s, expired_at = now()
                    WHERE video_id = %s
                """, (status, video_id))
            else:
                cur.execute("""
                    UPDATE marcus.video
                    SET status = %s
                    WHERE video_id = %s
                """, (status, video_id))
        conn.commit()


def expire_stale_videos(max_age_days=90):
    """Expire videos older than max_age_days (by published_at).

    Marks non-terminal videos as expired, removing them from the candidate pool.
    Returns list of expired video dicts.
    """
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                UPDATE marcus.video
                SET status = 'expired', expired_at = now()
                WHERE status NOT IN ('watched', 'skipped', 'expired')
                  AND published_at < now() - interval '%s days'
                RETURNING video_id, channel_id, title, status
            """, (max_age_days,))
            expired = cur.fetchall()
        conn.commit()
    return expired


# ── Programme build queries ─────────────────────────────────────────

def get_spanish_picks(target_seconds=2700, min_seconds=1800):
    """Select tier 4 (Spanish learning) videos for the daily programme.

    Fills a 30-45 minute block. Duration cap: 25 min per video.
    Within tier: newest first, deprioritise recently queued.

    target_seconds: 2700 = 45 min (upper bound)
    min_seconds: 1800 = 30 min (lower bound, best-effort)
    """
    DEFAULT_DURATION = 600  # 10 min for videos with unknown duration
    DURATION_CAP = 1500  # 25 min per video

    picks = []
    running_total = 0

    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT v.video_id, v.channel_id, c.channel_name, c.category,
                       v.title, v.description, v.published_at,
                       v.duration_seconds, v.thumbnail_url,
                       c.tier, v.last_queued_at, v.times_queued
                FROM marcus.video v
                JOIN marcus.channel c ON v.channel_id = c.channel_id
                WHERE c.tier = 4 AND c.subscribed = TRUE AND c.blacklisted = FALSE
                  AND v.published_at > now() - interval '90 days'
                  AND v.status NOT IN ('watched', 'skipped', 'expired')
                  AND COALESCE(v.duration_seconds, 0) >= 60
                  AND COALESCE(v.duration_seconds, %s) <= %s
                ORDER BY v.published_at DESC,
                         v.last_queued_at ASC NULLS FIRST
            """, (DEFAULT_DURATION, DURATION_CAP))

            for row in cur:
                dur = row["duration_seconds"] or DEFAULT_DURATION
                if running_total + dur > target_seconds:
                    continue
                picks.append(dict(row))
                running_total += dur

    return picks, running_total


def get_news_candidates():
    """Return tier 0 videos from the last 24 hours, <=5 min, for agent curation."""
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT v.video_id, v.channel_id, c.channel_name, c.category,
                       v.title, v.description, v.published_at,
                       v.duration_seconds, v.thumbnail_url
                FROM marcus.video v
                JOIN marcus.channel c ON v.channel_id = c.channel_id
                WHERE c.tier = 0 AND c.subscribed = TRUE AND c.blacklisted = FALSE
                  AND v.published_at > now() - interval '24 hours'
                  AND v.status NOT IN ('watched', 'skipped', 'expired')
                  AND COALESCE(v.duration_seconds, 0) <= 300
                ORDER BY v.published_at DESC
            """)
            return cur.fetchall()


def get_subscription_picks(target_seconds=18000, min_seconds=10800, tiers=None):
    """Mechanically select subscription videos for the daily programme.

    Fills from tier 1 (no duration cap), then tier 2 (<=25 min),
    then tier 3 (<=25 min). Within each tier: newest first, deprioritise
    recently queued. Stops at target_seconds. Returns ordered list.

    target_seconds: 18000 = 5 hours (upper bound)
    min_seconds: 10800 = 3 hours (lower bound, best-effort)
    tiers: list of tier numbers to include (default: [1, 2, 3])
    """
    DEFAULT_DURATION = 600  # 10 min for videos with unknown duration
    TIER_DURATION_CAP = {1: None, 2: 1500, 3: 1500}  # 25 min = 1500s

    if tiers is None:
        tiers = [1, 2, 3]

    picks = []
    running_total = 0

    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            for tier in tiers:
                if running_total >= target_seconds:
                    break

                cap = TIER_DURATION_CAP[tier]
                duration_filter = ""
                if cap is not None:
                    duration_filter = f"AND COALESCE(v.duration_seconds, {DEFAULT_DURATION}) <= {cap}"

                cur.execute(f"""
                    SELECT v.video_id, v.channel_id, c.channel_name, c.category,
                           v.title, v.description, v.published_at,
                           v.duration_seconds, v.thumbnail_url,
                           c.tier, v.last_queued_at, v.times_queued
                    FROM marcus.video v
                    JOIN marcus.channel c ON v.channel_id = c.channel_id
                    WHERE c.tier = %s AND c.subscribed = TRUE AND c.blacklisted = FALSE
                      AND v.published_at > now() - interval '90 days'
                      AND v.status NOT IN ('watched', 'skipped', 'expired')
                      AND COALESCE(v.duration_seconds, 0) >= 60
                      {duration_filter}
                    ORDER BY v.published_at DESC,
                             v.last_queued_at ASC NULLS FIRST
                """, (tier,))

                for row in cur:
                    dur = row["duration_seconds"] or DEFAULT_DURATION
                    if running_total + dur > target_seconds:
                        continue  # skip this one, might fit a shorter video
                    picks.append(dict(row))
                    running_total += dur

    return picks, running_total


def reset_playlist_statuses():
    """Reset all 'queued' videos back to 'new' for playlist rebuild.

    Clears playlist_item_id. Called before each daily rebuild.
    """
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE marcus.video
                SET status = 'new', playlist_item_id = NULL
                WHERE status = 'queued'
            """)
            count = cur.rowcount
        conn.commit()
    return count


def add_news_channel(channel_id, channel_name, category=None):
    """Add a tier 0 (news) channel. Not a YouTube subscription."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO marcus.channel
                    (channel_id, channel_name, tier, subscribed, category)
                VALUES (%s, %s, 0, TRUE, %s)
                ON CONFLICT (channel_id) DO UPDATE SET
                    channel_name = EXCLUDED.channel_name,
                    tier = 0,
                    subscribed = TRUE,
                    category = EXCLUDED.category,
                    updated_at = now()
            """, (channel_id, channel_name, category))
        conn.commit()


# ── Run log ─────────────────────────────────────────────────────────

def log_run(channels_checked, new_videos, queued, digest_posted=False, notes=None):
    """Insert a run_log entry. Returns the new row id."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO marcus.run_log
                    (channels_checked, new_videos, queued, digest_posted, notes)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (channels_checked, new_videos, queued, digest_posted, notes))
            row_id = cur.fetchone()[0]
        conn.commit()
    return row_id


# ── Playlist config ─────────────────────────────────────────────────

def get_playlist_config():
    """Get the cached playlist ID from a simple config table.

    Returns the playlist_id string or None.
    """
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT value FROM marcus.config
                WHERE key = 'playlist_id'
            """)
            row = cur.fetchone()
            return row[0] if row else None


def save_playlist_config(playlist_id):
    """Save the playlist ID to the config table."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO marcus.config (key, value)
                VALUES ('playlist_id', %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """, (playlist_id,))
        conn.commit()


# ── Conversation (session memory) ──────────────────────────────────

def log_conversation(message_text, response_text=None):
    """Insert a conversation row. Returns the new row id."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO marcus.conversation (message_text, response_text)
                VALUES (%s, %s)
                RETURNING id
            """, (message_text, response_text))
            row_id = cur.fetchone()[0]
        conn.commit()
    return row_id


def update_conversation_response(conversation_id, response_text):
    """Set the response_text on an existing conversation row."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE marcus.conversation
                SET response_text = %s
                WHERE id = %s
            """, (response_text, conversation_id))
        conn.commit()


def get_session_conversation(window_start):
    """Return conversation rows from window_start onward, ordered by time."""
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, message_text, response_text, created_at
                FROM marcus.conversation
                WHERE created_at >= %s
                ORDER BY created_at
            """, (window_start,))
            return cur.fetchall()


def search_conversation(query, limit=20):
    """Search conversation history by text (case-insensitive substring)."""
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, message_text, response_text, created_at
                FROM marcus.conversation
                WHERE message_text ILIKE %s OR response_text ILIKE %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (f"%{query}%", f"%{query}%", limit))
            return cur.fetchall()


# ── Channel stats (taste signals) ─────────────────────────────────

def upsert_channel_stats(channel_id, avg_completion, watch_count, skip_count,
                         quality_score):
    """Insert or update computed taste signals for a channel."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO marcus.channel_stats
                    (channel_id, avg_completion, watch_count, skip_count,
                     quality_score, last_computed)
                VALUES (%s, %s, %s, %s, %s, now())
                ON CONFLICT (channel_id) DO UPDATE SET
                    avg_completion = EXCLUDED.avg_completion,
                    watch_count = EXCLUDED.watch_count,
                    skip_count = EXCLUDED.skip_count,
                    quality_score = EXCLUDED.quality_score,
                    last_computed = now()
            """, (channel_id, avg_completion, watch_count, skip_count,
                  quality_score))
        conn.commit()


def get_channel_stats():
    """Return all channel stats rows."""
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT cs.channel_id, c.channel_name, cs.avg_completion,
                       cs.watch_count, cs.skip_count, cs.quality_score,
                       cs.last_computed
                FROM marcus.channel_stats cs
                JOIN marcus.channel c ON cs.channel_id = c.channel_id
                ORDER BY cs.quality_score DESC NULLS LAST
            """)
            return cur.fetchall()


def get_watch_data_for_stats():
    """Return per-channel watch/skip counts and avg completion for stats computation."""
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT channel_id,
                       count(*) FILTER (WHERE status = 'watched') AS watch_count,
                       count(*) FILTER (WHERE status = 'skipped') AS skip_count,
                       avg(completion_pct) FILTER (WHERE status = 'watched'
                                                     AND completion_pct IS NOT NULL)
                           AS avg_completion
                FROM marcus.video
                WHERE status IN ('watched', 'skipped')
                GROUP BY channel_id
            """)
            return cur.fetchall()


# ── Queue (playlist tracking) ─────────────────────────────────────

def insert_queue(video_ids, session_date=None):
    """Insert a batch of video IDs into the queue with sequential positions.
    Returns count inserted."""
    with connect() as conn:
        with conn.cursor() as cur:
            for pos, vid in enumerate(video_ids, 1):
                cur.execute("""
                    INSERT INTO marcus.queue (video_id, position, session_date)
                    VALUES (%s, %s, COALESCE(%s, current_date))
                """, (vid, pos, session_date))
        conn.commit()
    return len(video_ids)


def get_current_queue(session_date=None):
    """Return the queue for a session date (default today)."""
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT q.id, q.video_id, v.title, c.channel_name,
                       v.duration_seconds, q.position, q.status, q.created_at
                FROM marcus.queue q
                JOIN marcus.video v ON q.video_id = v.video_id
                JOIN marcus.channel c ON v.channel_id = c.channel_id
                WHERE q.session_date = COALESCE(%s, current_date)
                ORDER BY q.position
            """, (session_date,))
            return cur.fetchall()


def update_queue_status(queue_id, status):
    """Update the status of a queue entry."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE marcus.queue SET status = %s WHERE id = %s
            """, (status, queue_id))
        conn.commit()


def get_recently_queued_video_ids(days=7):
    """Return video IDs queued in the last N days, for deprioritization."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT video_id FROM marcus.queue
                WHERE session_date >= current_date - %s
            """, (days,))
            return {row[0] for row in cur.fetchall()}


# ── Blacklist ─────────────────────────────────────────────────────

def blacklist_channel(channel_id, reason=None):
    """Blacklist a channel. Does NOT delete — sets a flag."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE marcus.channel
                SET blacklisted = TRUE, blacklist_reason = %s, updated_at = now()
                WHERE channel_id = %s
            """, (reason, channel_id))
            count = cur.rowcount
        conn.commit()
    return count


def get_blacklisted_channels():
    """Return all blacklisted channels."""
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT channel_id, channel_name, blacklist_reason, updated_at
                FROM marcus.channel
                WHERE blacklisted = TRUE
                ORDER BY updated_at DESC
            """)
            return cur.fetchall()


def is_blacklisted(channel_id):
    """Check if a channel is blacklisted."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT blacklisted FROM marcus.channel WHERE channel_id = %s
            """, (channel_id,))
            row = cur.fetchone()
            return row[0] if row else False


# ── Curation candidates ──────────────────────────────────────────

def get_curation_candidates(max_duration=None, language=None,
                            exclude_channels=None, max_age_days=90):
    """Return candidate videos for model-driven curation.

    Joins channel stats when available. Respects blacklist.
    """
    conditions = [
        "c.subscribed = TRUE",
        "c.blacklisted = FALSE",
        "v.status NOT IN ('watched', 'skipped', 'expired')",
        "COALESCE(v.duration_seconds, 0) >= 60",
        f"v.published_at > now() - interval '{int(max_age_days)} days'",
    ]
    params = []

    if max_duration:
        conditions.append("v.duration_seconds <= %s")
        params.append(max_duration)
    if language == "spanish":
        conditions.append("c.tier = 4")
    if exclude_channels:
        conditions.append("c.channel_id != ALL(%s)")
        params.append(list(exclude_channels))

    where = " AND ".join(conditions)

    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                SELECT v.video_id, v.channel_id, c.channel_name, c.tier,
                       c.category, v.title, v.description, v.published_at,
                       v.duration_seconds, v.discovered,
                       v.last_queued_at, v.times_queued,
                       cs.avg_completion, cs.quality_score
                FROM marcus.video v
                JOIN marcus.channel c ON v.channel_id = c.channel_id
                LEFT JOIN marcus.channel_stats cs ON c.channel_id = cs.channel_id
                WHERE {where}
                ORDER BY cs.quality_score DESC NULLS LAST,
                         v.published_at DESC
            """, params)
            return cur.fetchall()


# ── Video completion tracking ─────────────────────────────────────

def set_video_watched(video_id, completion_pct=None):
    """Mark a video watched and store its completion percentage."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE marcus.video
                SET status = 'watched', completion_pct = %s
                WHERE video_id = %s
            """, (completion_pct, video_id))
        conn.commit()


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Marcus DB utilities")
    parser.add_argument("--check", action="store_true",
                        help="Quick connectivity check")
    parser.add_argument("--set-status", nargs=2, metavar=("VIDEO_ID", "STATUS"),
                        help="Set a video's status (e.g. watched, skipped)")
    parser.add_argument("--set-tier", nargs=2, metavar=("CHANNEL_ID", "TIER"),
                        help="Set a channel's tier (0=news, 1=must-watch, "
                             "2=priority, 3=filler, 4=spanish)")
    parser.add_argument("--find-channel", metavar="NAME",
                        help="Find channel IDs by name (case-insensitive substring)")
    parser.add_argument("--blacklist-channel", nargs="+", metavar=("CHANNEL_ID", "REASON"),
                        help="Blacklist a channel (ID, optional reason)")
    parser.add_argument("--list-blacklist", action="store_true",
                        help="List all blacklisted channels")
    args = parser.parse_args()

    if args.set_status:
        video_id, status = args.set_status
        valid = ("new", "queued", "watched", "skipped", "expired")
        if status not in valid:
            print(json.dumps({"error": f"Invalid status '{status}'. Must be one of: {', '.join(valid)}"}))
            sys.exit(1)
        update_video_status(video_id, status)
        print(json.dumps({"action": "set_status", "video_id": video_id, "status": status}))
    elif args.set_tier:
        channel_id, tier_str = args.set_tier
        try:
            tier = int(tier_str)
        except ValueError:
            print(json.dumps({"error": f"Tier must be an integer 0-4, got '{tier_str}'"}))
            sys.exit(1)
        try:
            set_channel_tier(channel_id, tier)
        except ValueError as e:
            print(json.dumps({"error": str(e)}))
            sys.exit(1)
        print(json.dumps({"action": "set_tier", "channel_id": channel_id, "tier": tier}))
    elif args.blacklist_channel:
        channel_id = args.blacklist_channel[0]
        reason = " ".join(args.blacklist_channel[1:]) if len(args.blacklist_channel) > 1 else None
        count = blacklist_channel(channel_id, reason)
        print(json.dumps({"action": "blacklist_channel", "channel_id": channel_id,
                          "reason": reason, "rows_affected": count}))
    elif args.list_blacklist:
        channels = get_blacklisted_channels()
        print(json.dumps({"action": "list_blacklist",
                          "channels": [dict(c) for c in channels]},
                         indent=2, default=str))
    elif args.find_channel:
        matches = find_channels_by_name(args.find_channel)
        print(json.dumps(
            {"action": "find_channel", "query": args.find_channel,
             "matches": [dict(m) for m in matches]},
            indent=2, default=str))
    else:
        # Default: connectivity check (same as --check)
        try:
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT current_database(), current_user, version()")
                    row = cur.fetchone()
                    cur.execute("""
                        SELECT table_name FROM information_schema.tables
                        WHERE table_schema = 'marcus'
                        ORDER BY table_name
                    """)
                    tables = [r[0] for r in cur.fetchall()]
            result = {
                "status": "connected",
                "database": row[0],
                "user": row[1],
                "pg_version": row[2],
                "marcus_tables": tables,
            }
        except Exception as e:
            result = {"status": "error", "error": str(e)}
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
