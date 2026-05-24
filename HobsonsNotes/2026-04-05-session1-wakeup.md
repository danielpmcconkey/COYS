# COYS Wakeup — 2026-04-05 Session 1

## What happened

Fixed two cron bugs that broke all scheduled agents on their first night.

### Bug 1: `claude` not on cron PATH
- **Symptom:** Bede posted error to Discord: `[Errno 2] No such file or directory: 'claude'`. Scotty silent (hadn't run yet due to Bug 2).
- **Cause:** `claude` lives at `/home/dan/.local/bin/claude`. Cron's `PATH` in `/etc/cron.d/coys` didn't include that directory.
- **Fix:** Prepended `/home/dan/.local/bin` to `PATH` in `/etc/cron.d/coys`.

### Bug 2: Cron schedule assumed UTC, system runs ET
- **Symptom:** Bede ran at 04:00/06:00 ET instead of 00:00/02:00 ET. Scotty scheduled for 10:00 ET instead of 06:00 ET. Marcus scheduled for 21:00 ET instead of 17:00 ET.
- **Cause:** Cron entries were written as UTC hours, but system cron uses local timezone (`America/New_York`).
- **Fix:** Changed schedule entries to local ET values: Scotty `0 6`, Marcus `0 17`, Bede `0 0,2,4`.

### Not yet verified
- No manual test run done. First live validation will be Bede at midnight ET.
- Comment text in `/etc/cron.d/coys` still has stale UTC annotations (cosmetic).

### Neil (from session 2, 2026-04-04)
- Parked. Agent files built, Phase 0 (Discord setup) not started.
- Open question: separate server vs role-restricted channel.

## State of COYS overall

- 5 of 6 original agents migrated. Thatcher deferred.
- Cron agents (Scotty, Marcus, Bede) have never completed a successful run through COYS.
- Interactive agents (Gabi, Zazu, Marcus listener) are running via systemd.
- OpenClaw gateway stopped, not uninstalled. Old agent repos awaiting archive.

## Key paths

- COYS repo: `/media/dan/fdrive/codeprojects/COYS/`
- Cron file: `/etc/cron.d/coys`
- Logs: `/media/dan/fdrive/codeprojects/COYS/logs/`
- Build plan: `/media/dan/fdrive/codeprojects/COYS/BUILD_PLAN.md`
