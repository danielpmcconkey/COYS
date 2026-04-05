# COYS

You are one of Dan's Discord agents running via COYS (the bot army HQ).
Your personality, instructions, and boundaries are in your own CLAUDE.md
(the one in your agent directory, not this file). This file is shared context.

## Dan

- GitHub: danielpmcconkey / danielpmcconkey@gmail.com
- Machine: Ubuntu Linux, kernel 6.8.0-71-generic
- Drives: fdrive (3.6TB at /media/dan/fdrive), edrive (~900GB at /media/dan/edrive)
- GPU: NVIDIA GTX 1080 (8GB VRAM)
- PostgreSQL: localhost, multiple databases (householdbudget, openclaw)

## Posting to Discord

Use the COYS discord helper to post messages to your channel:

```bash
python3 /media/dan/fdrive/codeprojects/COYS/lib/discord_post.py \
  --channel YOUR_CHANNEL_ID \
  --token-pass coys/YOUR_AGENT/discord-token \
  "Your message here"
```

Or pipe content:

```bash
echo "Your message" | python3 /media/dan/fdrive/codeprojects/COYS/lib/discord_post.py \
  --channel YOUR_CHANNEL_ID \
  --token-pass coys/YOUR_AGENT/discord-token
```

The helper handles chunking for Discord's 2000-character limit.

## Discord Formatting Rules

- Wrap URLs in angle brackets: `<https://example.com>` (suppresses embeds)
- No markdown tables — they render poorly on mobile. Use bullet lists.
- Keep messages concise. Dan reads on his phone.

## Secrets

- Never write secrets to files in this repo.
- Bot tokens are in the `pass` store under `coys/{agent}/discord-token`.
- Other credentials (DB, API keys) are in per-agent locations outside this repo.

## The Agent Roster

| Agent | Role | Channel |
|-------|------|---------|
| Scotty | System health monitor | #engine-room |
| Marcus | YouTube curator | #marcus_museum |
| Bede | Transcript historian | #archives |
| Gabi | Spanish tutor | #salon-de-clases |
| Zazu | Morning briefing | #morning-report |
| Thatcher | Finance categorizer | (TBD) |
