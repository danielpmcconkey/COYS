-- Marcus v2 schema additions
-- Run as the marcus DB user against the openclaw database.
--
-- New tables: conversation, channel_stats, queue
-- Modified tables: channel (blacklist), video (discovered, completion_pct)

BEGIN;

-- ── conversation (session memory) ─────────────────────────────────────
CREATE TABLE marcus.conversation (
    id          serial PRIMARY KEY,
    message_text  text NOT NULL,
    response_text text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_conversation_created ON marcus.conversation (created_at);

-- ── channel_stats (taste signals) ─────────────────────────────────────
CREATE TABLE marcus.channel_stats (
    channel_id    text PRIMARY KEY REFERENCES marcus.channel(channel_id),
    avg_completion  double precision,
    watch_count     int NOT NULL DEFAULT 0,
    skip_count      int NOT NULL DEFAULT 0,
    quality_score   double precision,
    last_computed   timestamptz NOT NULL DEFAULT now()
);

-- ── queue (playlist tracking) ─────────────────────────────────────────
CREATE TABLE marcus.queue (
    id          serial PRIMARY KEY,
    video_id    text NOT NULL REFERENCES marcus.video(video_id),
    position    int NOT NULL,
    session_date date NOT NULL DEFAULT current_date,
    status      text NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'playing', 'completed', 'skipped')),
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_queue_session ON marcus.queue (session_date);

-- ── channel: blacklist fields ─────────────────────────────────────────
ALTER TABLE marcus.channel
    ADD COLUMN blacklisted     boolean NOT NULL DEFAULT false,
    ADD COLUMN blacklist_reason text;

-- ── video: discovery flag + completion tracking ───────────────────────
ALTER TABLE marcus.video
    ADD COLUMN discovered      boolean NOT NULL DEFAULT false,
    ADD COLUMN completion_pct  double precision;

COMMIT;
