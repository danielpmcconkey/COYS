# COYS — Build Plan

## What This Is

COYS is Dan's bot army HQ. A monorepo that replaces OpenClaw as the
orchestration layer for all Discord agents. No framework, no daemon, no
third-party platform. Just system cron, `claude -p`, discord.py, and thin
Python glue.

From Anthropic's perspective, Dan is using Claude Code from the terminal.
That's it. Covered by the Max subscription.

---

## Architecture

Two execution models, one shared library, per-agent directories.

### Model 1: Cron Agents (Scotty, Marcus, Bede)

```
system crontab
  → bin/run-agent {agent-name}
    → cd agents/{agent}/
    → claude -p "{task prompt}" [flags]
    → agent runs scripts, generates report, posts to Discord itself
    → wrapper logs result and handles failures
```

The agent IS Claude Code running in the agent's directory. It picks up the
agent's `CLAUDE.md` (personality + instructions), runs the agent's Python
scripts via Bash tool, and posts to Discord using a shared `post_discord.py`
helper. The wrapper script just provides the trigger, timeout, and error
handling.

### Model 2: Interactive Agents (Gabi, Zazu, Thatcher)

```
systemd service: coys@{agent}.service
  → bin/listen {agent-name}
    → discord.py bot connects with agent's token
    → on message from Dan:
      → claude -p "{context + message}" [flags] in agent dir
      → bot posts Claude's response back to Discord
```

One generic `listen` script, parameterised by agent name. Reads agent config
for token, channel, model. The discord.py bot is a thin proxy — it shuttles
messages between Discord and `claude -p`. All intelligence comes from the
agent's CLAUDE.md.

Each interactive agent runs as a separate systemd service with its own bot
token, so each agent appears in Discord as itself.

### `claude -p` Invocation

Standard flags for all agents:

```bash
claude -p "{prompt}" \
  --model {agent_model} \
  --permission-mode dontAsk \
  --allowed-tools "Read Write Edit Bash Grep Glob" \
  --no-session-persistence \
  --output-format text
```

| Flag | Why |
|------|-----|
| `-p` | Non-interactive. Print and exit. |
| `--model` | Sonnet for most. Opus for Bede. |
| `--permission-mode dontAsk` | Agents run unattended. No prompts. |
| `--allowed-tools` | Restrict to what agents need. No web search, no MCP. |
| `--no-session-persistence` | Cron runs don't need session history. Saves disk. |
| `--output-format text` | Plain text. Interactive bots capture stdout. |

The agent's `CLAUDE.md` is auto-discovered because `claude -p` runs from
inside the COYS git repo, in the agent's subdirectory. Claude Code reads:
1. `COYS/CLAUDE.md` (shared context — Dan's info, the agent roster)
2. `COYS/agents/{name}/CLAUDE.md` (personality, instructions, boundaries)

### Shared Library (`lib/`)

~200 lines of Python. Four modules:

| Module | Purpose |
|--------|---------|
| `runner.py` | Subprocess wrapper for `claude -p`. Sets cwd, timeout, captures output, returns exit code + stdout/stderr. |
| `discord_post.py` | Posts messages to Discord via bot token + REST API. Handles chunking (2000 char limit), basic error reporting. Agents call this from their scripts. |
| `config.py` | Loads agent config from `agents/{name}/config.yaml`. Returns typed dataclass. |
| `log.py` | Consistent logging. File + stdout. One log per agent per day under `logs/`. |

The lib is pip-installable (`pip install -e .`) so agent scripts can
`from coys.lib import discord_post`.

---

## Directory Structure

```
COYS/
├── BUILD_PLAN.md
├── CLAUDE.md                  # Shared context (Dan's info, agent roster, conventions)
├── pyproject.toml             # Package definition for lib
├── bin/
│   ├── run-agent              # Cron entry point (bash)
│   └── listen                 # Interactive bot runner (python)
├── lib/
│   ├── __init__.py
│   ├── runner.py
│   ├── discord_post.py
│   ├── config.py
│   └── log.py
├── agents/
│   ├── scotty/
│   │   ├── CLAUDE.md          # Personality + instructions
│   │   ├── config.yaml        # Channel, model, schedule, timeout
│   │   └── scripts/
│   │       ├── requirements.txt
│   │       └── run_health_check.py
│   ├── marcus/
│   │   ├── CLAUDE.md
│   │   ├── config.yaml
│   │   └── scripts/
│   │       ├── requirements.txt
│   │       ├── auth.py
│   │       ├── subscriptions.py
│   │       ├── rss_check.py
│   │       ├── metadata.py
│   │       ├── playlist.py
│   │       ├── db.py
│   │       ├── digest.py
│   │       └── run_daily.py
│   ├── bede/
│   │   ├── CLAUDE.md
│   │   ├── config.yaml
│   │   └── scripts/
│   │       ├── requirements.txt
│   │       ├── discover.py
│   │       └── update_registry.py
│   ├── gabi/
│   │   ├── CLAUDE.md
│   │   ├── config.yaml
│   │   └── scripts/
│   │       ├── requirements.txt
│   │       └── homework_status.py
│   ├── zazu/
│   │   ├── CLAUDE.md
│   │   ├── config.yaml
│   │   └── scripts/
│   ├── thatcher/
│   │   ├── CLAUDE.md
│   │   ├── config.yaml
│   │   └── scripts/
│   │       ├── requirements.txt
│   │       ├── parse_fidelity.py
│   │       ├── parse_secu.py
│   │       ├── parse_amazon.py
│   │       ├── categorize.py
│   │       ├── dedup.py
│   │       └── process_inbox.py
│   └── ...
├── systemd/
│   └── coys@.service          # Template unit. Instance = agent name.
├── cron/
│   └── coys                   # Drop-in for /etc/cron.d/
└── logs/                      # gitignored. Per-agent, per-day.
```

---

## Agent Roster

### Scotty — System Health Monitor
- **Mode:** Cron
- **Schedule:** `0 10 * * *` UTC (06:00 ET)
- **Timeout:** 600s
- **Model:** Sonnet
- **Channel:** `#engine-room` (1484232297644298250)
- **Delivery:** Agent posts directly (not wrapper-delivered)
- **Scripts:** `run_health_check.py` — gathers local system metrics + Synology NAS health via REST API
- **External deps:** NAS creds in `pass` (`openclaw/scotty/nas-*`), PostgreSQL (status check only), Docker (status check only)
- **Migration notes:** Simplest agent. One script, no DB writes, no API tokens. Good first migration. Currently agent posts her own report — preserve this pattern.

### Bede — Transcript Historian
- **Mode:** Cron
- **Schedule:** `0 4,6,8 * * *` UTC (00:00, 02:00, 04:00 ET)
- **Timeout:** 1200s
- **Model:** Opus (premium quality for transcript analysis)
- **Channel:** `#archives` (1482354239748571206)
- **Delivery:** Announce (wrapper captures + posts)
- **Scripts:** `discover.py` (find new transcripts, limit 5), `update_registry.py` (log entries)
- **External deps:** Transcript directories (Hobson + BD, read-only), journal dir (read-only), summary output dir (write)
- **Migration notes:** Needs `--add-dir` for transcript directories outside the COYS repo. Delivery mode is "announce" — OpenClaw currently captures output and posts. We can either switch to agent-posts-directly or have the wrapper capture + post. Agent-posts-directly is more consistent with the other cron agents.

### Marcus — YouTube Curator
- **Mode:** Cron + Interactive
- **Schedule:** `0 21 * * *` UTC (17:00 ET)
- **Timeout:** 900s
- **Model:** Sonnet
- **Channel:** `#marcus_museum` (1483924993145438420)
- **Delivery:** Announce (wrapper captures + posts)
- **Scripts:** 8 scripts — auth.py, subscriptions.py, rss_check.py, metadata.py, playlist.py, db.py, digest.py, run_daily.py
- **External deps:** YouTube Data API (OAuth token at marcus/.youtube_token.json, client secret at marcus/.client_secret.json), PostgreSQL (`openclaw.marcus` schema, .pgpass at marcus/.pgpass)
- **Migration notes:** Most complex cron agent. Has interactive commands too (Dan sends "queue that" etc. in Discord). For the cron run, `run_daily.py` orchestrates everything. Interactive commands need the discord.py bot — so Marcus is both cron AND interactive. The cron run posts the daily digest; the interactive bot handles ad-hoc commands. Credential files stay outside the repo — `--add-dir` or symlinks.
- **Dual-mode design:** Cron fires `run_daily.py` for the daily digest. Interactive bot handles Dan's commands. Same CLAUDE.md, same scripts, two entry points.

### Gabi — Spanish Tutor
- **Mode:** Interactive
- **Channel:** `#salón-de-clases` (1487189344639910089)
- **Model:** Sonnet
- **Scripts:** `homework_status.py` (reads aprendiendo repo)
- **External deps:** `/media/dan/fdrive/codeprojects/aprendiendo/` (read-only)
- **Migration notes:** Simple interactive agent. One script + Q&A. Needs `--add-dir` for aprendiendo repo. Reads latest wakeup notes from aprendiendo/hobsons_notes/ for calibration.

### Zazu — Morning Briefing
- **Mode:** Interactive
- **Channel:** `#morning-report` (1476537750239973482)
- **Model:** Sonnet
- **Scripts:** `fetch_email.py` (Gmail API — overnight emails), `fetch_rss.py` (Reddit, HN, Yahoo Finance, Al Jazeera, Reuters, BBC)
- **External deps:** Gmail API via `pass` (`openclaw/zazu/gmail-credentials`, `openclaw/zazu/gmail-token`), `feedparser`, `google-api-python-client`, `google-auth-oauthlib`
- **Personality:** Zazu from The Lion King. Fussy hornbill majordomo. Dan summons with "Zazu! Report!" — he snaps to attention like Mufasa just bellowed from Pride Rock.
- **Source:** Lives at `~/.openclaw/workspace/` as the `main` OpenClaw agent (not a separate repo). IDENTITY.md, SKILL.md with full personality spec, two scripts with venv.
- **Migration notes:** Straightforward interactive agent. Copy scripts, compose CLAUDE.md from IDENTITY.md + SKILL.md. Discord token is the `default` account in OpenClaw config (separate from the other bot tokens). RSS feeds include r/coys — naturally.

### Thatcher — Finance Transaction Categorizer
- **Mode:** Interactive (approval flow)
- **Channel:** TBD (1476961966491959367 in OpenClaw config)
- **Model:** Sonnet
- **Scripts:** 6 scripts — three parsers (Fidelity CSV, SECU PDF, Amazon CSV), categorize.py, dedup.py, process_inbox.py
- **External deps:** Financial data at `/media/dan/fdrive/thatcher-data/` (outside repo), PostgreSQL (`householdbudget.personalfinance` schema), .pgpass outside repo
- **Migration notes:** Most complex agent overall. Approval flow requires the discord.py bot to handle reactions/replies — Dan approves/rejects categorizations via Discord. This is beyond the generic `listen` bot template and needs custom message handling. Migrate last. **Finance data must never touch this repo.**

---

## Agent Config Format

`agents/{name}/config.yaml`:

```yaml
name: scotty
emoji: "\U0001F527"  # 🔧
mode: cron            # cron | interactive | dual
model: sonnet         # sonnet | opus

discord:
  channel_id: "1484232297644298250"
  token_pass: "openclaw/scotty/discord-token"   # path in pass store

cron:
  schedule: "0 10 * * *"        # UTC
  timeout_seconds: 600
  prompt: "Run your daily health check. Post the report to Discord."
  delivery: self                 # self (agent posts) | capture (wrapper posts)

extra_dirs:                      # passed as --add-dir
  - /media/dan/fdrive/some/path
```

Interactive agent example (Gabi):

```yaml
name: gabi
emoji: "\U0001F1F2\U0001F1FD"  # 🇲🇽
mode: interactive
model: sonnet

discord:
  channel_id: "1487189344639910089"
  token_pass: "openclaw/gabi/discord-token"

extra_dirs:
  - /media/dan/fdrive/codeprojects/aprendiendo
```

Dual-mode agent example (Marcus):

```yaml
name: marcus
emoji: "\U0001F3DB\UFE0F"  # 🏛️
mode: dual
model: sonnet

discord:
  channel_id: "1483924993145438420"
  token_pass: "openclaw/marcus/discord-token"

cron:
  schedule: "0 21 * * *"
  timeout_seconds: 900
  prompt: "Run your daily curation. Use run_daily.py."
  delivery: self

extra_dirs: []
```

---

## Credential Management

**Tokens move to `pass`.** Currently in `~/.openclaw/openclaw.json` (plaintext).
Migrate to `pass` store under `coys/{agent}/discord-token`. This is a one-time
manual step (Dan or Hobson).

**Other credentials stay where they are:**
- NAS creds: `pass` under `openclaw/scotty/nas-*` (already there)
- YouTube API: `marcus/.youtube_token.json` and `.client_secret.json` (outside repo)
- DB creds: `.pgpass` files per agent (outside repo)

**Nothing in the repo. Ever.** `.gitignore` covers `*.token`, `.pgpass`,
`*.secret*`, `.env`, `logs/`, `*.pyc`, `__pycache__/`, `.venv/`.

---

## Cron Setup

Drop-in file at `/etc/cron.d/coys`:

```cron
# COYS — Bot Army Cron
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin
COYS_HOME=/media/dan/fdrive/codeprojects/COYS

# Scotty — 06:00 ET (10:00 UTC)
0 10 * * * dan $COYS_HOME/bin/run-agent scotty

# Marcus — 17:00 ET (21:00 UTC)
0 21 * * * dan $COYS_HOME/bin/run-agent marcus

# Bede — 00:00, 02:00, 04:00 ET (04:00, 06:00, 08:00 UTC)
0 4,6,8 * * * dan $COYS_HOME/bin/run-agent bede
```

`bin/run-agent` (bash, ~30 lines):
1. Load agent config
2. `cd agents/{name}/`
3. Run `claude -p` with flags from config
4. Log stdout/stderr to `logs/{agent}/{date}.log`
5. On failure: post error summary to agent's Discord channel
6. Exit

---

## Systemd Services

Template unit at `systemd/coys@.service`:

```ini
[Unit]
Description=COYS Discord Bot — %i
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=dan
WorkingDirectory=/media/dan/fdrive/codeprojects/COYS
ExecStart=/media/dan/fdrive/codeprojects/COYS/bin/listen %i
Restart=on-failure
RestartSec=30
Environment=COYS_HOME=/media/dan/fdrive/codeprojects/COYS

[Install]
WantedBy=default.target
```

Enable per interactive agent:
```bash
systemctl --user enable coys@gabi
systemctl --user enable coys@zazu
systemctl --user enable coys@thatcher
# Marcus (dual-mode) also needs the listener:
systemctl --user enable coys@marcus
```

---

## Dependencies

**Shared (lib + bin):**
- Python 3.11+
- `discord.py` (2.x)
- `pyyaml`
- `requests` (for Discord REST API posting from agents)

**Per-agent script deps (isolated venvs):**
- Scotty: `requests` (NAS API)
- Marcus: `google-api-python-client`, `google-auth-oauthlib`, `feedparser`, `psycopg2-binary`
- Bede: (none beyond stdlib, reads/writes files)
- Thatcher: `pdfplumber`, `psycopg2-binary`
- Zazu: `google-api-python-client`, `google-auth-oauthlib`, `feedparser`
- Gabi: (none beyond stdlib)

Each agent's `scripts/` directory gets its own `.venv/`. The CLAUDE.md tells
the agent which Python to use (`scripts/.venv/bin/python`).

---

## Migration Order

Simplest first. Prove the pattern, then scale.

| # | Agent | Mode | Complexity | Why this order |
|---|-------|------|------------|----------------|
| 1 | Scotty | Cron | Low | One script, no DB writes, no API tokens. Proves the cron pattern. |
| 2 | Gabi | Interactive | Low | One script, simple Q&A. Proves the interactive pattern. |
| 3 | Bede | Cron | Medium | Multiple external dirs, Opus model, longer timeout. |
| 4 | Marcus | Dual | High | 8 scripts, YouTube API, DB, cron + interactive. |
| 5 | Zazu | Interactive | Medium | Gmail + RSS scripts exist. Needs Gmail token refresh testing. |
| 6 | Thatcher | Interactive | High | Approval flow, financial data, custom Discord handling. |

Each migration:
1. Create agent directory in COYS
2. Compose CLAUDE.md from existing SOUL.md + USER.md + TOOLS.md + IDENTITY.md
3. Copy scripts (NOT venvs — recreate from requirements.txt)
4. Write config.yaml
5. Migrate Discord bot token to `pass`
6. Test with manual `claude -p` invocation
7. Set up cron entry or systemd service
8. Verify Discord output matches current behaviour
9. Disable old OpenClaw cron job / agent
10. Archive old GitHub repo (after all agents migrated)

---

## Resolved Questions

1. **EDT/EST transitions:** UTC only. Dan adjusts manually when clocks change.
2. **Marcus dual-mode:** Fresh `claude -p` per message. No session persistence.
3. **Thatcher approval flow:** May not need Discord at all. Everything is local.
   Could use `claude -p` interactively or another local interface. Design when
   we get there.
4. **`~/.claude/CLAUDE.md`:** Hobson's problem to sort out before migration.
5. **Subscription dependency:** Noted. Cross that bridge if it comes to it.
6. **Zazu's Discord token:** Working as-is. Use existing `default` bot token.
