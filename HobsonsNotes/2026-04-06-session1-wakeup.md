# COYS Wakeup — 2026-04-06 Session 1

## What happened

Built and deployed **Pollan** — meal planning coach bot. Sixth COYS agent, first new agent since the isolation migration.

### Pollan agent

- Character: Michael Pollan's voice. "Eat food. Not too much. Mostly plants."
- Mode: dual (cron + interactive)
- Discord: `#the-hearth`, channel ID `1490683853701120140`
- OS user: `pollan`, in `coys` group, Claude auth complete
- Systemd: `coys@pollan.service` — running, verified
- State dir: `/home/pollan/grocery-lists/`
- Scripts: `generate_grocery_pdf.py` (JSON → PDF), `discord_upload.py` (file → Discord)
- Venv: `agents/pollan/scripts/.venv/` — fpdf2, requests

### Dietary model (baked into CLAUDE.md)

- Dan: plant-forward Mediterranean, cutting animal protein. Legumes, tofu, grains, veg, olive oil. Occasional fish from frozen.
- Wife: no seafood, no cilantro. Loves beef/chicken. Happy with same batch protein all week.
- Fork model: shared plant-forward base, she adds batch protein (frozen portions from Saturday prep), cilantro on Dan's plate only.
- Weekend prep: Souper Cubes for stews/beans, squeeze bottles for sauces, batch her protein.
- Weeknight window: 5-6 PM, carbon steel cookware.

### PDF grocery list

- Font: DejaVu Sans bold for title, DejaVu Serif for body
- Sizes: title 13, headers 10 bold, items 10, footer 8 italic
- Went through 3 rounds of font/size adjustments — started too large, ended compact
- Checkbox: `[ ]` (ASCII — Unicode ballot box not in serif fonts)
- Output: `/home/pollan/grocery-lists/YYYY-MM-DD.pdf`, also posted to Discord as attachment

### Infrastructure improvements

- **New agent playbook:** `~/penthouse-pete/coys-new-agent-playbook.md` — paint-by-numbers for adding any new agent. Phases 0-5.
- **Generic setup script:** `~/penthouse-pete/setup-coys-agent.sh` — takes agent name as argument. Case statement for per-agent state dirs. Replaces one-off scripts.
- COYS roster in `CLAUDE.md` updated with Pollan entry.

### Issues encountered

- Pollan timed out on Discord interactive (120s) when given a large pantry inventory + meal plan + grocery list in one message. Workaround: break into steps or use interactive `claude` terminal session from agent dir.
- Dan put pantry inventory in `/tmp/ingredients_on_hand.txt` since it was too large for Discord. Copied to `/tmp/` so pollan user could read it.
- `dan` user needed ACL on `/home/pollan/` for convenience: `sudo setfacl -R -m u:dan:rwX /home/pollan` + default ACL.
- CLAUDE.md boundary "Do NOT modify scripts" was too strict — relaxed to allow changes when Dan explicitly asks.

### Cron — NOT YET CONFIGURED

Pollan's cron schedule is designed but not added to `/etc/cron.d/coys`:
- Friday 22:00 UTC (6 PM ET): weekly plan + grocery PDF
- Saturday 14:00 UTC (10 AM ET): shopping nag
- Daily 19:30 UTC (3:30 PM ET): dinner reminder
- Daily 00:30 UTC (8:30 PM ET): accountability check

## Still to do

- **Add cron entries** to `/etc/cron.d/coys` for Pollan's schedule
- **Validate cron flow** — run-agent uses the single prompt from config.yaml; Pollan checks day/time and acts accordingly. Untested.
- **First full week** — Pollan did pantry audit and meal planning interactively today. Friday cron cycle will be the first automated run.
- **Neil** — parked. Agent files built, Phase 0 not started.
- **Thatcher** — deferred. Not in COYS.

## Key paths

- Agent dir: `/media/dan/fdrive/codeprojects/COYS/agents/pollan/`
- State: `/home/pollan/` (pantry.json, weekly-plan.json, cooking-log.json, grocery-lists/)
- New agent playbook: `~/penthouse-pete/coys-new-agent-playbook.md`
- Generic setup script: `~/penthouse-pete/setup-coys-agent.sh`
- Migration runbook: `~/penthouse-pete/coys-migration-runbook.md`
