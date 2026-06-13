# Marcus v2 — From Newspaper Editor to DJ

**Date:** 2026-05-29
**Status:** Requirements complete, ready for planning
**Scope:** Deep — feature (existing product, fundamental redesign)

## Problem

Marcus is a rigid, tier-based cron job that builds a YouTube playlist once a
day at 5pm and hopes it's right by 9pm. Dan gets the same long-form content
from the same few channels every night (Mr. Beat, Vlogging Through History
monopolize the queue). Marcus can't take on-the-fly requests, doesn't learn
from watch patterns, has no conversation memory, and can't evaluate content
quality. His rules are too deterministic — designed for dumb models using
mechanical scripts.

Dan wants a DJ, not a newspaper editor.

## Users

Dan. One user. On the couch at night, phone in hand (Discord), Shield TV on
the wall (SmartTube). Too zapped to curate for himself, wants to say "gimme
7 short ones, skip the news" and have it happen.

## Core Experience

### The Evening Flow

1. Dan gets on the couch, opens Discord, tells Marcus what kind of evening
   he's having: mood, energy level, topic preferences, time budget.
2. Marcus builds a queue in seconds from his catalog — taste-aware, varied,
   right-sized — and pushes it directly to SmartTube on the Shield via ADB.
3. Dan watches. Marcus observes (watch-sync) and learns.
4. If Dan wants to adjust mid-session ("more like that last one" / "enough
   science, switch to Spanish"), Marcus rebuilds on the fly.

### Taste Learning

Marcus infers Dan's preferences primarily from observed behavior:

- **Completion rates** — consistently bailing at 20% = channel has a problem;
  95%+ = gold
- **Skip patterns** — what Dan skips tells Marcus what to deprioritize
- **Time-of-day preferences** — news in the evening vs. not, Spanish on
  certain nights
- **Length preferences** — inferred from what Dan actually watches vs. skips
- **Channel quality scores** — built over time from completion data
- **Explicit feedback** — "that was AI slop", "more of this", "I'm done with
  news" — captured and persisted permanently

Marcus maintains a living preferences document autonomously. Dan rarely needs
to manage it directly. When he does give explicit feedback, Marcus remembers
it permanently and generalizes (e.g., three AI-narration rejections across
different channels = "AI narration = avoid" as a taste rule).

### Content Discovery

Marcus actively discovers new content outside Dan's existing subscriptions:

- Finds new channels based on what Dan watches and likes
- Adds discovered videos to queues with commentary ("trying this one —
  similar to Wendover, 12 minutes on logistics")
- Dan watches or skips; Marcus learns from the outcome
- **Rejections are permanent.** If Dan says "don't show me this channel,"
  Marcus records a blacklist entry — not a deletion. The channel stays in
  the database with a rejected/banned status so Marcus never rediscovers
  and re-adds it.

Discovery source (YouTube search API, related videos, or other mechanism)
is a planning decision.

### Conversation Memory

- **Active window: 2PM - 2AM daily.** Marcus has full conversational context
  within this window. "I told you 20 minutes ago to skip the news" works.
- **Archive:** All conversations are stored. Marcus can search history on
  demand when Dan asks ("what did I tell you about that channel last week?").
- **Taste persistence:** Preferences learned from conversations persist
  permanently in the taste profile, independent of conversation archives.

### Content Quality Assessment

- **Channel-level reputation**, not per-video screening
- Built from two sources: watch-sync completion data (automatic) and
  explicit feedback (Dan says "AI narrator" or "clickbait")
- Once a channel is flagged for a quality issue, the flag applies to all
  future videos from that channel
- **No pre-hoc AI narration detection.** YouTube is working on content
  labeling; Marcus will integrate that signal when it ships. Until then,
  post-hoc feedback is the mechanism.

## What Changes from Current Marcus

### Cron Job: Infrastructure, Not Product

The daily cron becomes catalog maintenance:
- Sync RSS feeds for new uploads
- Enrich metadata (title, duration, thumbnails)
- Expire old videos
- Sync subscriptions
- Run discovery passes (find new channels/content)
- Update taste model from accumulated watch-sync data

The cron no longer builds the playlist. It maintains the catalog that the
interactive session draws from.

### Queue Delivery: ADB Direct, Not YouTube Playlist API

SmartTube accepts video URLs via ADB intents. Marcus pushes queues directly
to the Shield — no YouTube playlist API round-trip, no quota cost, no rate
limits, near-instant delivery.

The existing YouTube playlist ("Marcus Queue") can be deprecated or kept as
a fallback, but it's no longer the primary delivery mechanism.

### Tier System: Soft Context, Not Hard Rules

Existing tier data (200+ channels with Dan's expressed preferences) stays
as institutional knowledge. But tiers stop being the algorithm:

- No more hardcoded duration caps per tier
- No more mechanical "newest first within tier" ordering
- No more fixed playlist structure (news block / spanish block / subs block)
- The model decides what to include based on: the request, the taste
  profile, variety pressure, recency, and channel quality scores

Variety pressure is critical — the current system's biggest failure is
showing the same 3-4 channels every night because they upload most
frequently and are tier 1.

### Interactive Mode: Stateful Sessions

The Discord listener evolves from stateless `claude -p` per-message to a
session-aware system that maintains context within the 2PM-2AM daily window.

## Non-Goals

- **Multi-Shield support** — one Shield, one user, until a second box exists
- **Pre-hoc AI content detection** — defer to YouTube's labeling efforts
- **Comment scraping** — too noisy, too expensive, low ROI
- **Video content inspection** — no downloading or analyzing actual video/audio
- **Other household members** — Marcus serves Dan only
- **Mobile viewing** — Shield is the target device; phone/tablet viewing
  is out of scope

## Success Criteria

1. Dan can say "gimme 7 short ones" and have them playing on the Shield
   within 30 seconds
2. No single channel appears more than twice in a queue unless Dan
   specifically requests it
3. Marcus surfaces new content Dan hasn't seen before at least once per
   session
4. After 2 weeks of use, Marcus's inferred taste profile produces queues
   Dan doesn't need to adjust most nights
5. Dan never sees a video from a channel he explicitly rejected

## Dependencies and Assumptions

- **Shield ADB connectivity** — must be reliable for both queue delivery
  and watch-sync. Current issue: Shield becomes unreachable after router
  reboots (discovered 2026-05-29). Needs investigation.
- **YouTube Data API quota** — discovery features will consume more quota
  than the current RSS-only approach. Needs quota budgeting during planning.
- **Opus model cost** — Dan is willing to pay for better judgment. Curation
  decisions use Opus; fast acknowledgments can stay on Sonnet.
- **ADB queue delivery mechanism** — needs proof-of-concept. SmartTube
  accepts individual video intents; queueing multiple videos sequentially
  via ADB needs validation.
- **Session memory architecture** — the `bin/listen` infrastructure is
  shared across all COYS agents. Session persistence for Marcus must not
  break Zazu, Gabi, Pollan, etc.

## Open Questions for Planning

1. **Discovery source** — what mechanism does Marcus use to find new content
   outside subscriptions? YouTube search API, related videos API, or
   something else?
2. **ADB queue protocol** — can SmartTube accept a playlist-style queue
   via ADB, or does Marcus need to send videos one at a time? What happens
   when a video ends — does SmartTube auto-advance?
3. **Session memory implementation** — per-agent session files? Database
   table? How does the 2PM-2AM window reset work?
4. **Taste model storage** — does the current `preferences.json` evolve,
   or does Marcus need a richer data structure for inferred preferences
   vs. explicit preferences?
5. **Watch-sync data aggregation** — how does Marcus turn raw completion
   events into channel quality scores and taste patterns? Batch analysis
   during cron, or continuous?
