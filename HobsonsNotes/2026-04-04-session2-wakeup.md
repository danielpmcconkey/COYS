# COYS Wakeup — 2026-04-04 Session 2

## What happened

Built **Neil** — a biology and math tutor agent for Dan's daughter. She's a
sophomore at Appalachian State studying nutrition. Thinks she's bad at both
subjects; the confidence problem is the core design challenge.

### Neil agent
- **Mode:** Interactive
- **Model:** Sonnet
- **Persona:** NDT energy — infectious curiosity, warm authority, explains the
  why, connects everything back to nutrition. Not an impression. The approach.
- **Core pedagogy:** Guide, never solve. Name specific wins. Normalise difficulty.
  Reframe "I'm bad at this" with evidence, not cheerleading.
- **Subject scope:** Bio (A&P, biochem, cell bio, micro) + Math (stats primarily,
  possibly precalc/applied calc). All framed through nutrition.

### Files created
- `agents/neil/CLAUDE.md` — personality, pedagogy, subject areas, boundaries
- `agents/neil/config.yaml` — channel_id is `TBD`, token at `coys/neil/discord-token`
- `agents/neil/scripts/` — empty (no scripts needed, pure tutoring)
- Root `CLAUDE.md` roster updated with Neil

### Dan's Phase 0 (not yet done)
1. Create Discord bot "Neil" in Developer Portal, copy token
2. Create a Discord channel (e.g., `#neils-lab`)
3. Invite bot to server
4. `pass insert coys/neil/discord-token`
5. Update `agents/neil/config.yaml` with real channel_id
6. `systemctl --user enable --now coys@neil`

### Open question
Dan's current Discord server is his bot army ops server. His daughter probably
shouldn't see `#engine-room` and `#archives`. Options: separate server for Neil,
or restrict her Discord role to Neil's channel only.

## State of COYS overall

Per session 1 wakeup (still current):
- 5 of 6 original agents migrated. Bede, Marcus, Zazu untested through COYS.
- Thatcher not migrated (may not need Discord).
- OpenClaw gateway stopped, not uninstalled.
- Old agent repos awaiting archive.
- Scotty still checks for `openclaw_gateway` (expected inactive now).

## Key paths

- COYS repo: `/media/dan/fdrive/codeprojects/COYS/`
- Neil agent: `/media/dan/fdrive/codeprojects/COYS/agents/neil/`
- Neil CLAUDE.md: `/media/dan/fdrive/codeprojects/COYS/agents/neil/CLAUDE.md`
- Build plan: `/media/dan/fdrive/codeprojects/COYS/BUILD_PLAN.md`
- Session 1 wakeup: `/media/dan/fdrive/codeprojects/COYS/HobsonsNotes/2026-04-04-session1-wakeup.md`
