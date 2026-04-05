# COYS Wakeup — 2026-04-04 Session 1

## What happened

Built COYS from scratch in a single session. OpenClaw is shuttered.

### The trigger
Anthropic cut third-party tool access from subscriptions (2026-04-04).
OpenClaw agents became metered (~$0.72/run). Dan got a $200 credit expiring
April 17. Rather than migrate to Anthropic's native features (deeper lock-in),
we built our own replacement.

### What COYS is
A monorepo at `/media/dan/fdrive/codeprojects/COYS/` that replaces OpenClaw.
System cron + `claude -p` + discord.py listeners + thin Python glue. From
Anthropic's perspective, Dan is using Claude Code from the terminal.

- Repo: `danielpmcconkey/COYS` — pushed to GitHub
- BUILD_PLAN.md has the full architecture spec

### What's running
- **OpenClaw gateway:** STOPPED (`systemctl --user stop openclaw-gateway.service`)
- **COYS listeners:** `coys@gabi`, `coys@zazu`, `coys@marcus` — systemd user services, running
- **COYS cron:** installed at `/etc/cron.d/coys` — Scotty 06:00, Marcus 17:00, Bede 00/02/04 (all EDT/UTC)

### Agents migrated (5 of 6)

| Agent | Mode | Status | Tested |
|-------|------|--------|--------|
| Scotty | Cron | Migrated | Yes — posted to #engine-room via claude -p |
| Gabi | Interactive | Migrated | Yes — live conversation in Discord via COYS listener |
| Bede | Cron | Migrated | Not yet (cron will fire at midnight) |
| Marcus | Dual | Migrated | Listener running, cron set for 17:00 |
| Zazu | Interactive | Migrated | Listener running, not yet tested through COYS |
| Thatcher | Deferred | Not migrated | May not need Discord — local-only possible |

### Issues found and fixed
- YAML unicode escapes (`\U0001F527`) don't work — switched to literal emoji
- Scotty's health check still checks `openclaw_gateway` — will report it as
  inactive, which is now expected. CLAUDE.md notes this.

### Issues outstanding
- **Bede, Marcus, Zazu not yet tested through COYS.** First real test is when
  cron fires or Dan invokes them in Discord.
- **Thatcher not migrated.** Dan suggested he might not need Discord at all.
  Design when we get there.
- **OpenClaw gateway disabled but not uninstalled.** Can be re-enabled if
  needed during the transition.
- **Old agent repos still exist.** Archive after confirming COYS is stable.
- **Scotty's `openclaw_gateway` check** should eventually be replaced with
  COYS systemd service checks.

## Key paths

- COYS repo: `/media/dan/fdrive/codeprojects/COYS/`
- Build plan: `/media/dan/fdrive/codeprojects/COYS/BUILD_PLAN.md`
- Shared lib: `/media/dan/fdrive/codeprojects/COYS/lib/`
- Agent dirs: `/media/dan/fdrive/codeprojects/COYS/agents/{name}/`
- Cron runner: `/media/dan/fdrive/codeprojects/COYS/bin/run-agent`
- Interactive listener: `/media/dan/fdrive/codeprojects/COYS/bin/listen`
- Root venv: `/media/dan/fdrive/codeprojects/COYS/.venv/`
- Discord tokens: `pass` under `coys/{agent}/discord-token`
- Systemd template: `~/.config/systemd/user/coys@.service`
- Cron file: `/etc/cron.d/coys`

## Resume prompt

```
Hobson, read the wakeup at /media/dan/fdrive/codeprojects/COYS/HobsonsNotes/2026-04-04-session1-wakeup.md. We're working on COYS.
```
