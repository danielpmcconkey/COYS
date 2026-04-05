# COYS Wakeup — 2026-04-05 Session 2

## What happened

Migrated all 5 active agents to per-user OS isolation. Each agent now runs
as its own Linux user with its own Claude OAuth session and file-based secrets.

### Agent isolation

- Created OS users: scotty, bede, marcus, gabi, zazu
- Created `coys` group for shared repo read access
- ACLs for traverse on mount path (/media/dan, /media/dan/fdrive, /media/dan/fdrive/codeprojects)
- ACL on /home/dan (traverse only) so agents can reach the claude binary
- Symlink: /usr/local/bin/claude → /home/dan/.local/bin/claude
- System-level systemd template at /etc/systemd/system/coys@.service (User=%i)
- Old user-level template removed

### Secrets migration

- All agents: Discord tokens extracted from `pass` to /home/{agent}/.discord-token
- Scotty: NAS host/credentials to /home/scotty/.nas-host, .nas-credentials
- Marcus: YouTube client-secret, youtube-token, pgpass to /home/marcus/
- Zazu: Gmail credentials and token to /home/zazu/
- Lib code updated: `get_token()` supports both token_file and token_pass
- discord_post.py CLI: --token-file and --token-pass as mutually exclusive args
- Agent scripts updated: pass → file reads (auth.py, db.py, run_health_check.py, fetch_email.py)

### Marcus taste system

- New `~/.preferences.json` — Marcus reads before cron, updates on interactive feedback
- Sections: channel_notes, topic_boosts, topic_dampens, taste_notes
- Feedback updates preferences for future runs, does NOT modify current playlist
- Tested live: Dan gave feedback about Mr. Beat and Vlogging Through History, Marcus logged it correctly

### Issues discovered and fixed during migration

- Agent dirs were chowned to agent users, locking Hobson out of configs. Fixed: dan:coys ownership, agents read via group.
- Mount path (/media/dan, /media/dan/fdrive, /media/dan/fdrive/codeprojects) blocked traversal. Fixed with coys:x ACLs.
- `sudo -u` vs `sudo -i -u`: the former doesn't set HOME, so claude auth lands in wrong dir. Must use `-i`.
- Bede needs rwX on TranscriptSummaries/ (not just rX on ai-dev-playbook).

### All agents verified

| Agent | Mode | Status |
|-------|------|--------|
| scotty | cron | Ran health check, posted to Discord as scotty user |
| bede | cron | Ran transcript cycle as bede user |
| marcus | dual | Cron tested, interactive listener running as marcus user |
| gabi | interactive | Listener running as gabi user, tested in Discord |
| zazu | interactive | Listener running as zazu user |

## Still to do

- **Expand Gabi** — full Spanish teaching loop (homework creation, grading, Anki batches, progress logging). Discussed and agreed in this session, not yet implemented.
- **Neil** — parked. Agent files built, Phase 0 (Discord setup) not started. Will need own user when ready.
- **Thatcher** — deferred. Not in COYS.

## Key paths

- COYS repo: `/media/dan/fdrive/codeprojects/COYS/`
- Migration runbook: `~/penthouse-pete/coys-migration-runbook.md` (private, not in repo)
- Setup script: `~/penthouse-pete/setup-coys-users.sh` (infrastructure baseline for new agents)
- Cron file: `/etc/cron.d/coys`
- System systemd template: `/etc/systemd/system/coys@.service`
- Marcus preferences: `/home/marcus/.preferences.json`
