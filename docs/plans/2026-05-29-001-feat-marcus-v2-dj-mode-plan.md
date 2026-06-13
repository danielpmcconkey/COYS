---
title: "feat: Marcus v2 — DJ Mode"
status: active
origin: docs/brainstorms/marcus-v2-requirements.md
created: 2026-05-29
depth: deep
---

# Marcus v2 — DJ Mode

## Problem Frame

Marcus is a rigid cron job that builds a YouTube playlist once a day using
mechanical tier rules. Dan gets the same long-form content from the same few
channels every night. Marcus can't take on-the-fly requests, doesn't learn
from watch patterns, has no conversation memory, and can't evaluate content
quality.

Dan wants to get on the couch and say "I had a long day, gimme 3 hours of
easy stuff" and have the right videos playing on the Shield within 90 seconds.

(see origin: `docs/brainstorms/marcus-v2-requirements.md`)

---

## Scope Boundaries

### In Scope

- On-demand playlist building triggered by Dan via Discord
- Conversation memory within a 2PM-2AM daily window
- Taste learning from watch-sync completion data and explicit feedback
- Content discovery via YouTube Search API
- Channel blacklist/rejection system
- ADB playlist push to SmartTube on Shield
- Marcus-specific Discord listener (decoupled from shared `bin/listen`)

### Out of Scope

- Multi-Shield support
- Pre-hoc AI narration detection
- Comment scraping or video content inspection
- Other household members
- Mobile viewing

### Deferred to Follow-Up Work

- YouTube AI content labeling integration (when YouTube ships it)
- Scheduled cron removal (disable after v2 is proven stable)

---

## Key Technical Decisions

### 1. Kill the cron — catalog refresh on first request

**Decision:** No daily cron job. Marcus refreshes the catalog (RSS sync,
metadata enrichment, expiration, discovery) as the first step when Dan
requests a queue. Subsequent requests in the same session skip the refresh.

**Rationale:** The cron built a playlist Dan might not use. Catalog refresh
takes <60 seconds (RSS is parallel/free, metadata is batched). Removes a
moving part. Marcus is idle until Dan speaks.

### 2. Keep YouTube playlist as delivery mechanism

**Decision:** Marcus rebuilds the YouTube playlist on-demand via the API,
then pushes the playlist URL to SmartTube via ADB intent. SmartTube plays
it natively with a browsable queue and auto-advance.

**Rationale:** Tested 2026-05-29 — SmartTube plays playlist URLs natively.
ADB `am start` with individual video URLs interrupts the current video
(no queue intent exists in SmartTube). Playlist API quota cost is ~700
units per 7-video rebuild; even 3 rebuilds/night is well under the daily
cap. The rate limit Dan hit previously was from automated repeated rebuilds,
not from on-demand use.

**Constraint:** Marcus never rebuilds the playlist without Dan's explicit
trigger via Discord.

### 3. Marcus gets his own listener (decoupled from `bin/listen`)

**Decision:** Fork `bin/listen` into a Marcus-specific listener that adds
conversation memory. The shared `bin/listen` stays unchanged for Zazu,
Gabi, Pollan.

**Rationale:** The 2026-05-18 incident proved that shared `bin/listen`
changes break all agents. Session persistence is fundamentally incompatible
with the stateless model the other agents rely on. Separate listener =
separate systemd service = restarts don't cascade.

### 4. Conversation memory via log + context prefix

**Decision:** Each Discord message/response pair is logged to a DB table
(`marcus.conversation`). On each invocation, the listener loads all messages
from the current 2PM-2AM window and feeds them as a context prefix to
`claude -p`. Older history is archived and searchable on demand.

**Rationale:** Preserves the "fresh Claude per message" pattern that makes
CLAUDE.md and script changes take effect immediately. No long-running Claude
process holding 12 hours of state in memory. The 2PM-2AM window keeps
context size bounded — a busy evening might be 20-30 message pairs, well
within the context window.

### 5. Dual taste model — DB for signals, JSON for sentiments

**Decision:** Quantitative taste signals (channel completion rates, quality
scores, skip counts) live in a DB table (`marcus.channel_stats`). Qualitative
preferences (Dan's expressed sentiments, topic boosts/dampens, taste notes)
stay in `~/.preferences.json`. Both are loaded into the curation prompt.

**Rationale:** Completion rates and skip counts are computed from watch-sync
data — relational, aggregatable, naturally DB-shaped. Dan's expressed
preferences ("I don't like AI narrators", "more cooking shows") are
free-text notes that Marcus reads and applies with judgment — naturally
document-shaped. The dual model keeps each in its natural form.

### 6. Model-driven curation replaces mechanical scripts

**Decision:** The model (Opus) is the curation engine. It receives: Dan's
request, the taste profile (DB stats + preferences), the available catalog
(queried via scripts), and variety constraints. It picks videos using
judgment, not tier rules. Existing tier data stays as soft context
("Dan told me this is a must-watch channel") but doesn't drive selection.

**Rationale:** The tier system's biggest failure is showing Mr. Beat and
Vlogging Through History every night because they're tier 1 and upload
frequently. A model can balance recency, variety, mood, and taste
simultaneously. That's the whole point of paying for Opus.

### 7. Variety pressure as an explicit constraint

**Decision:** The curation prompt includes explicit variety rules: no
channel appears more than twice in a queue, subject diversity is required,
and recently-queued videos are deprioritized. These are prompt instructions,
not script logic.

**Rationale:** Hardcoded variety rules would recreate the rigidity problem.
Prompt-level instructions let the model balance variety against Dan's
specific request ("give me all the Spanish content you have" might
legitimately need 3 videos from one channel).

---

## Implementation Units

### U1. Schema additions

**Goal:** Add database tables for conversation memory, queue tracking,
channel statistics, and blacklist support.

**Requirements:** Conversation memory, taste learning, rejection permanence
(see origin).

**Dependencies:** None — foundation for everything else.

**Files:**
- `agents/marcus/scripts/migrations/001-v2-schema.sql` (new)
- `agents/marcus/scripts/db.py` (modify — add new query functions)

**Approach:**

New tables:

`marcus.conversation` — message log for session memory.
Columns: id (serial PK), message_text, response_text, created_at.
The 2PM-2AM window is a query filter, not a structural boundary.

`marcus.channel_stats` — computed taste signals per channel.
Columns: channel_id (FK/PK), avg_completion (float), watch_count (int),
skip_count (int), quality_score (float), last_computed (timestamp).

`marcus.queue` — tracks what's in the current playlist and its order.
Columns: id (serial PK), video_id (FK), position (int), session_date (date),
status (pending/playing/completed/skipped), created_at.

Modify `marcus.channel`: add `blacklisted` boolean (default false),
`blacklist_reason` text (nullable). Blacklisted channels are excluded
from all curation queries.

Modify `marcus.video`: add `discovered` boolean (default false) to
distinguish videos found via discovery from subscription content.

Add query functions to `db.py`: conversation CRUD, channel stats
read/write, queue management, blacklist operations, catalog queries
that respect blacklist and include stats.

**Patterns to follow:** Existing `db.py` pattern — raw SQL via psycopg2,
functions per operation, no ORM.

**Test scenarios:**
- Insert and retrieve conversation messages filtered by time window
- Channel stats upsert — update existing, insert new
- Blacklisted channel excluded from `get_active_channels` results
- Queue insert with position ordering, status transitions
- Discovered video flag preserved through status changes
- Conversation window boundary: message at 1:59 PM excluded, 2:00 PM included
- Blacklist reason preserved when channel is blacklisted

**Verification:** Migration runs cleanly against the `openclaw` database.
All new `db.py` functions have passing tests. Existing functions unaffected.

---

### U2. Marcus-specific listener

**Goal:** Fork `bin/listen` into a Marcus-specific listener with conversation
memory, decoupled from the shared listener.

**Requirements:** Conversation memory, stateful sessions, session memory
must not break other agents (see origin).

**Dependencies:** U1 (conversation table).

**Files:**
- `agents/marcus/listen` (new)
- `systemd/coys-marcus-interactive.service` (new)
- `agents/marcus/scripts/db.py` (modify — conversation functions from U1)

**Approach:**

Fork `bin/listen` into `agents/marcus/listen`. Changes from the shared
version:

1. On message receipt: log Dan's message to `marcus.conversation` via
   `db.py`.
2. Before invoking `claude -p`: query today's conversation window
   (messages where created_at >= today 2PM ET, or yesterday 2PM if
   current time is before 2PM). Format as a conversation transcript
   and prepend to the Claude invocation as context.
3. On response: log Marcus's response to the same conversation row.
4. Remove `--no-session-persistence` — but each invocation is still a
   fresh `claude -p` process. Session context comes from the conversation
   log prefix, not from Claude's session persistence.

New systemd service `coys-marcus-interactive.service` replaces
`coys@marcus.service` for Marcus only. Other agents keep using
`coys@.service` template unchanged.

The conversation prefix format:
```
=== Earlier today ===
[14:32] Dan: skip the news tonight
[14:32] Marcus: Noted — no news in tonight's queue.
[21:15] Dan: gimme 7 short ones, nothing heavy
[21:16] Marcus: Building your queue now...
=== Current message ===
```

**Patterns to follow:** `bin/listen` structure — discord.py client, message
handler, Claude subprocess invocation. Keep the typing indicator, chunked
responses, DM support.

**Test scenarios:**
- Conversation log written on each message/response pair
- Context prefix includes only messages from current 2PM-2AM window
- Window rolls correctly at 2PM (messages before 2PM excluded after rollover)
- Messages from previous days excluded from active context
- Listener handles Discord reconnects without losing conversation state
- Other agents (Zazu, Gabi, Pollan) unaffected — still using shared listener
- Context prefix doesn't exceed reasonable size (~30 message pairs)

**Verification:** Marcus responds with awareness of earlier messages in the
same session. "I told you 20 minutes ago to skip the news" works. Zazu/Gabi
still function on the shared listener.

---

### U3. Catalog refresh script

**Goal:** Consolidate the catalog maintenance steps from `run_daily.py` into
a standalone script that Marcus calls on first request of the evening.

**Requirements:** Curation draws from a fresh catalog (see origin).

**Dependencies:** U1 (discovered flag on video table).

**Files:**
- `agents/marcus/scripts/refresh_catalog.py` (new)
- `agents/marcus/scripts/run_daily.py` (retain for reference, eventually remove)

**Approach:**

New script that runs the catalog maintenance pipeline:
1. Sync RSS feeds (reuse `rss_check.py` — parallel, 20 workers, free)
2. Enrich new video metadata (reuse `metadata.py` — batched YouTube API)
3. Expire videos >90 days old (reuse existing expiry logic from `db.py`)
4. Run discovery pass (see U7 — initially a no-op stub)
5. Output JSON summary: new videos found, channels checked, expired count

Designed to complete in <60 seconds. Called by Marcus via the curation
prompt before building a queue. Marcus decides whether to refresh based
on conversation context (skip if already refreshed this session).

**Patterns to follow:** `run_daily.py` structure — orchestrator that calls
existing modules. JSON output to stdout for Claude to read.

**Test scenarios:**
- RSS check runs in parallel across all subscribed channels
- New videos enriched with metadata and inserted into DB
- Shorts (<60s) filtered out during enrichment
- Videos >90 days old expired
- Discovery stub returns empty results without error
- Output JSON contains accurate counts
- Script completes in <60 seconds for ~200 channels

**Verification:** Script runs end-to-end, catalog is fresh, output JSON
is parseable by Claude.

---

### U4. Taste aggregation

**Goal:** Compute channel quality scores and taste signals from watch-sync
completion data.

**Requirements:** Taste learning from completion rates, skip patterns,
channel quality scores (see origin).

**Dependencies:** U1 (channel_stats table), existing watch-sync data in
`marcus.video` (status=watched with completion data).

**Files:**
- `agents/marcus/scripts/taste.py` (new)
- `agents/marcus/scripts/db.py` (modify — stats query functions from U1)

**Approach:**

New script that aggregates watch-sync data into channel statistics:

1. For each channel with watched/skipped videos, compute:
   - Average completion rate (from watch-sync position data — needs a
     `completion_pct` column on `marcus.video`, populated by watch-sync)
   - Watch count vs. skip count
   - Quality score: weighted formula of completion rate and watch/skip ratio
2. Upsert results into `marcus.channel_stats`
3. Output summary for Claude to reference during curation

Called by `refresh_catalog.py` as part of the catalog maintenance pipeline,
or standalone.

Requires extending `watch_sync.py` to store `completion_pct` on the video
row when marking watched (currently it only sets status, not the percentage).

**Patterns to follow:** `db.py` for data access. Script outputs JSON summary.

**Test scenarios:**
- Channel with 10 watched videos at 90%+ completion gets high quality score
- Channel with 5 watched, 5 skipped gets medium quality score
- Channel with mostly skips gets low quality score
- New channel with no watch data gets no stats row (not zero score)
- Stats update is idempotent (re-running doesn't change results)
- Completion percentage stored correctly by watch-sync extension

**Verification:** Channel stats populated in DB. Quality scores correlate
with watch behavior (high-completion channels score higher than
high-skip channels).

---

### U5. On-demand curation and queue build

**Goal:** Marcus builds a playlist from Dan's request, taste profile, and
catalog — then pushes it to SmartTube.

**Requirements:** Evening flow, variety pressure, model-driven curation,
ADB delivery (see origin).

**Dependencies:** U1 (queue table), U3 (fresh catalog), U4 (taste data).

**Files:**
- `agents/marcus/scripts/curate.py` (new)
- `agents/marcus/scripts/build_playlist.py` (modify)
- `agents/marcus/scripts/queue_push.py` (new)
- `agents/marcus/CLAUDE.md` (modify — new curation instructions)

**Approach:**

**`curate.py`** — Queries the catalog for candidate videos and returns them
as structured data for Claude to curate from. Inputs: optional filters
(max duration, language, exclude channels, exclude recently queued).
Output: JSON list of candidates with title, channel, duration, tier,
quality score, times previously queued, discovered flag.

The model (Opus) does the actual curation — picking which candidates to
include based on Dan's request, the taste profile, and variety constraints.
`curate.py` provides the data; Claude provides the judgment.

**`build_playlist.py`** — Already exists. Modify to accept the curated
video list from Claude's decision, not from the mechanical pipeline.
The clear-and-rebuild pattern stays. Add a flag to skip the digest post
(digest moves to the interactive response).

**`queue_push.py`** — Sends the playlist URL to SmartTube via ADB intent.
Reuses the ADB helper pattern from `watch_sync.py` (dedicated server port
5038, graceful disconnect handling). Records the queue in `marcus.queue`
for tracking.

**Curation prompt flow** (in CLAUDE.md):
1. If catalog not refreshed this session, run `refresh_catalog.py`
2. Run `curate.py` with filters derived from Dan's request
3. Apply taste profile (preferences.json + channel_stats) to select videos
4. Enforce variety: no channel >2x unless explicitly requested
5. Include 1-2 discovered/new-channel videos with commentary
6. Run `build_playlist.py` with the selected video IDs
7. Run `queue_push.py` to push playlist to SmartTube
8. Respond in Discord with the queue summary and any discovery notes

**Key constraint:** Marcus NEVER rebuilds the playlist without Dan's
explicit trigger via Discord. Feedback is noted but not acted on until
Dan asks for a new queue.

**Patterns to follow:** Existing `build_playlist.py` for playlist API
interaction. `watch_sync.py` for ADB patterns.

**Test scenarios:**
- Candidate query returns videos from subscribed, non-blacklisted channels
- Candidates include quality scores when available
- Discovered videos flagged in candidate output
- Playlist rebuild clears old items and inserts new in order
- ADB push sends playlist URL to SmartTube successfully
- Queue tracking records all videos with positions
- No channel appears >2x in a 7-video queue (unless requested)
- Recently queued videos deprioritized in candidates
- Empty catalog (no candidates) returns graceful message, not error
- Playlist not rebuilt without explicit Dan trigger

**Verification:** Dan says "gimme 7 short ones," Marcus builds and pushes a
playlist to the Shield within 90 seconds. SmartTube shows a browsable queue.
Queue is varied — not the same 3 channels.

---

### U6. Blacklist and rejection system

**Goal:** Permanent channel rejection that survives rediscovery.

**Requirements:** Rejections are permanent, Dan never sees rejected channels
(see origin).

**Dependencies:** U1 (blacklist fields on channel table).

**Files:**
- `agents/marcus/scripts/db.py` (modify — blacklist functions)
- `agents/marcus/CLAUDE.md` (modify — blacklist commands)

**Approach:**

Add `db.py` functions:
- `blacklist_channel(channel_id, reason)` — sets `blacklisted=true`,
  records reason. Does NOT delete the row.
- `get_blacklisted_channels()` — returns all blacklisted channels.
- Modify all candidate/active-channel queries to exclude blacklisted
  channels (`WHERE blacklisted = false`).

Add interactive commands to CLAUDE.md: "drop channel X" / "never show me X
again" → calls `db.py --blacklist-channel`.

When Marcus discovers a channel (U7), he checks the blacklist before adding.
If the channel is blacklisted, it's silently skipped.

**Patterns to follow:** Existing `db.py --find-channel` / `--set-tier` CLI
pattern for the new `--blacklist-channel` command.

**Test scenarios:**
- Blacklisted channel excluded from `get_active_channels`
- Blacklisted channel excluded from curation candidates
- Blacklist reason preserved and queryable
- Blacklist survives subscription sync (sync doesn't reset blacklist)
- Discovery skips blacklisted channels
- Dan can ask Marcus to show blacklisted channels ("who did I ban?")
- Blacklist is additive only — no accidental unblacklist

**Verification:** Dan says "never show me Use Your Spanish again." The
channel is blacklisted. It never appears in future queues, even if Marcus
rediscovers it.

---

### U7. Content discovery

**Goal:** Marcus finds new channels and videos outside Dan's subscriptions.

**Requirements:** Content discovery, discovered videos flagged in queue
(see origin).

**Dependencies:** U1 (discovered flag), U5 (curation pipeline), U6
(blacklist check).

**Files:**
- `agents/marcus/scripts/discover.py` (new)
- `agents/marcus/scripts/refresh_catalog.py` (modify — integrate discovery)
- `agents/marcus/scripts/db.py` (modify — discovery query functions)

**Approach:**

**Discovery mechanism:** YouTube Search API (`search.list`). Cost: 100
quota units per search call.

**Discovery strategy (run during catalog refresh):**
1. Load Dan's top-performing channels (highest quality scores from
   channel_stats) and extract their categories/topics
2. Run 2-3 targeted searches per session based on these topics
   (e.g., "cooking technique", "personal finance explainer")
3. Filter results: exclude known channels (subscribed or blacklisted),
   exclude Shorts, require English or Spanish
4. Enrich metadata for discovered videos
5. Insert into DB with `discovered=true`

**Quota budget:** 2-3 searches per session = 200-300 units. Combined with
playlist rebuild (~700 units) and metadata enrichment (~50 units), total
session cost is ~1,050 units. Well under the daily cap even with multiple
sessions.

**Discovery in curation:** When building a queue, Marcus includes 1-2
discovered videos and notes them in Discord ("trying this one — similar
to Wendover, 12 min on shipping logistics"). Dan's watch/skip behavior
on discovered content feeds back into taste learning.

**Patterns to follow:** `metadata.py` for YouTube API usage patterns.
`auth.py` for OAuth service creation.

**Test scenarios:**
- Search returns results filtered to exclude known channels
- Blacklisted channels excluded from discovery results
- Discovered videos inserted with `discovered=true`
- Duplicate discovery (same video found twice) handled gracefully
- Discovery respects quota budget (max 3 searches per session)
- Discovered video appears in curation candidates with flag
- Discovery with zero results returns empty, not error

**Verification:** After catalog refresh, new videos from undiscovered
channels appear in the catalog with `discovered=true`. Marcus includes
one in a queue and notes it to Dan in Discord.

---

### U8. CLAUDE.md rewrite

**Goal:** Replace Marcus's rigid curation instructions with v2 behavior —
on-demand DJ mode, taste-aware, conversational.

**Requirements:** All v2 behavioral requirements (see origin).

**Dependencies:** U2 (conversation memory), U5 (curation pipeline),
U6 (blacklist), U7 (discovery).

**Files:**
- `agents/marcus/CLAUDE.md` (rewrite)

**Approach:**

Rewrite the instruction surface to reflect v2 behavior:

**Persona:** Keep Marcus Brody character. Add DJ framing — he reads the
room, not a spreadsheet.

**Core flow:**
1. Wait for Dan's request (never build unprompted)
2. On first request of session: refresh catalog (call `refresh_catalog.py`)
3. Query candidates (call `curate.py` with filters from request)
4. Apply taste profile: read `~/.preferences.json` + query channel_stats
5. Select videos with judgment — variety, mood match, discovery mix
6. Build playlist and push to Shield
7. Respond with queue summary in Discord

**Feedback handling:**
- Note feedback in conversation and in preferences
- Do NOT rebuild playlist on feedback alone
- Wait for explicit trigger ("build me a new one", "next queue")
- Generalize patterns (3 AI-narration rejections → taste rule)

**Interactive commands (updated):**
- Request a queue: natural language ("gimme 7 short ones")
- Rebuild: "new queue", "build me another", "refresh"
- Feedback: "I skipped X because...", "more like X", "that was great"
- Blacklist: "never show me X again", "drop X permanently"
- Taste check: "what do you think I like?", "show me my preferences"
- History: "what did I tell you last week about..."
- Discovery: "find me something new about cooking"

**Removed:**
- Rigid tier-based curation procedure (4-step daily build)
- Mechanical duration caps and ordering rules
- Daily digest posting
- The "scripts are your staff" framing (scripts are tools, model is curator)

**Patterns to follow:** Existing CLAUDE.md structure (personality section,
commands section, boundaries). Keep it under 300 lines.

**Test scenarios:**
- Marcus responds to natural language queue requests
- Marcus refuses to rebuild without explicit trigger
- Marcus notes feedback without acting on it
- Marcus references earlier conversation from the same session
- Marcus includes discovery notes when surfacing new channels
- Marcus can explain his taste model ("what do you think I like?")

**Verification:** Dan interacts with Marcus v2 in Discord through a full
evening flow — request, watch, feedback, rebuild — and Marcus behaves
as described in the requirements.

---

### U9. Extend watch-sync for taste data

**Goal:** Store completion percentage when marking videos watched, enabling
taste aggregation.

**Requirements:** Taste learning from completion rates (see origin).

**Dependencies:** U1 (completion_pct column on video table — add in U1
migration).

**Files:**
- `agents/marcus/scripts/watch_sync.py` (modify)
- `agents/marcus/scripts/db.py` (modify — update watched function)

**Approach:**

Currently `watch_sync.py` marks a video as `watched` when completion
reaches 85%. It knows the exact completion percentage but doesn't store it.

Changes:
1. Add `completion_pct` float column to `marcus.video` (in U1 migration)
2. Modify the `set_video_status` call in `watch_sync.py` to pass the
   completion percentage
3. Modify `db.py`'s watched-update function to store `completion_pct`

This is a small change that enables all of U4's taste aggregation.

**Patterns to follow:** Existing `watch_sync.py` completion detection logic.

**Test scenarios:**
- Video marked watched at 92% stores completion_pct = 0.92
- Video marked watched at 100% stores completion_pct = 1.0
- Completion percentage persists through DB queries
- Existing watch-sync behavior unchanged (85% threshold still applies)

**Verification:** After watching a video, `marcus.video` row shows both
`status='watched'` and the actual completion percentage.

---

## Sequencing

```
U1 (schema) ─┬─► U2 (listener) ─────────────────────────► U8 (CLAUDE.md)
              ├─► U3 (catalog refresh) ──► U5 (curation) ─┘
              ├─► U9 (watch-sync ext) ──► U4 (taste agg) ─┘
              └─► U6 (blacklist) ──► U7 (discovery) ──────┘
```

**Recommended build order:** U1 → U9 → U2 → U3 → U6 → U4 → U5 → U7 → U8

U8 (CLAUDE.md rewrite) comes last because it depends on all the scripts
and infrastructure being in place. Each prior unit can be built and tested
independently.

---

## System-Wide Impact

- **Other COYS agents:** Unaffected. Marcus gets his own listener; shared
  `bin/listen` is unchanged. Zazu, Gabi, Pollan continue as-is.
- **Marcus cron:** Disabled once v2 is stable. The `/etc/cron.d/coys` entry
  for Marcus (17:00 ET) gets commented out.
- **Watch-sync service:** Minor extension (completion_pct). Service stays
  running, no behavioral change.
- **YouTube API quota:** Net reduction. Daily playlist rebuild (~3000 units)
  eliminated. On-demand rebuilds (~700/session) + discovery (~300/session)
  total ~1000 units per evening vs. ~3000 daily before.
- **Shield ADB:** No change to connectivity model. Queue push reuses the
  proven ADB patterns from watch-sync.

---

## Risks and Mitigations

**Shield ADB connectivity after router reboots.** Discovered 2026-05-29 —
the Shield becomes unreachable until power cycled. This blocks both
watch-sync and queue delivery. Mitigation: investigate root cause
separately. For now, document the power-cycle workaround. The system
degrades gracefully — Marcus can still curate and respond in Discord;
he just can't push to the Shield until connectivity is restored.

**Conversation context size.** A busy evening could generate 30+ message
pairs. At ~200 tokens per pair, that's ~6000 tokens of prefix context.
Well within limits, but worth monitoring. If it becomes an issue,
summarize older messages and keep only the last 10 verbatim.

**Opus cost for interactive curation.** Each queue build is one Opus
invocation with catalog data + taste profile + conversation context.
Expect ~$0.10-0.30 per curation call. Acceptable for 1-3 calls per
evening. Fast acknowledgments ("noted, I'll remember that") can use
Sonnet to save cost.

**YouTube OAuth token expiry.** The OAuth app may still be in GCP test
mode (7-day token expiry). Under heavier interactive use, this could
cause auth failures. Mitigation: verify and publish the OAuth app, or
handle re-auth gracefully in scripts.
