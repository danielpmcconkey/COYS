# Postgres backup — sonofleo_prod

| When (ET) | Script | Does |
|---|---|---|
| 03:15 daily | `pg-backup-nightly.sh` | `pg_dump` to `/mnt/media/Backups/postgres/sonofleo_prod/sonofleo_prod-YYYY-MM-DD.dump`, checked with `pg_restore --list` before it takes its name |
| 03:45 daily | `pg-backup-prune.sh` | Deletes dumps older than 14 days, never a `-01` one, never the newest 14. `DRY_RUN=1` to preview |
| 04:30 daily | `pg-backup-offsite.sh` | Puts every dump on `gdrive-crypt:` (encrypted Drive), so Drive holds what the NAS does: 14 dailies plus every `-01`. `-01` dumps: copy only, never deleted or overwritten. Dailies: `rclone sync` (pruned ones leave Drive, no trash), `--immutable`, `--max-delete 2`. `cryptcheck`, writes `.offsite-status.json` |
| 03:30 Sundays | `records-backup-weekly.sh` | `tar.gz` of `/mnt/media/BusinessRecords` to `/mnt/media/Backups/businessrecords/BusinessRecords-YYYY-MM-DD-HHMM.tar.gz`, checked with `tar -tzf`; prunes to 5 weeks (never the newest 5, never the first archive of a month); `rclone sync` to `gdrive-crypt:businessrecords`, so pruned archives leave Drive too (no trash); `cryptcheck`, writes `.offsite-status.json` |
| 06:00 daily | Scotty | Newest dump < 26h and readable; this month's `-01` present; off-site < 26h and has the newest dump. Newest records archive < 8 days, readable, and verified in Drive |

Runs as `dan` (cron in `/etc/cron.d/coys`). Logs: `COYS/logs/backup/YYYY-MM-DD.log`.
Role `sonofleo_backup` (read-only via `pg_read_all_data`), password in `~dan/.pgpass`.
The records archives restore with the same Recovery steps below: they're under
`businessrecords/` instead of `postgres/sonofleo_prod/`, then `tar -xzf`.

## One-time setup

### 1. Root setup (terminal, ~2 min)

```
sudo bash /media/dan/fdrive/codeprojects/COYS/backup/setup-root.sh
```

Installs rclone, creates the role and `.pgpass`, makes the NAS folders, moves
the LeoBloom final dump to `/mnt/media/Backups/postgres/leobloom_prod/`, adds
the cron lines, takes the first dump. Ends with a listing showing today's file.

### 2. (Skipped) Own Google OAuth client

Not needed: rclone's built-in client is published and verified, so its login
doesn't expire, and one small file a month is nowhere near its rate limits.
Your own client needs a published app, which Google now gates behind a
branding page with an external URL (2026-10-24). Only revisit if uploads
start failing on rate limits.

### 3. Encryption passwords (Keeper, ~2 min)

In a new Keeper record, "Backup — rclone Google Drive", use Keeper's generator to add two fields:
**Encryption password** and **Encryption salt** (32+ characters each, different).
In the record's notes, paste the "Recovery" section below.

### 4. Connect rclone (terminal — your own, not Claude's `!`, ~3 min)

```
bash /media/dan/fdrive/codeprojects/COYS/backup/setup-rclone.sh
```

Press Enter at the two client prompts, then paste the two encryption values
from Keeper. A browser tab opens: sign in to Google and Allow. The script
finishes with a round-trip test and shows Drive holding gibberish file names.

### 5. Tell Hobson

Hobson checks the log, the first dump and Scotty's next report.

## Recovery (paste this into the Keeper record)

Needs only a browser, this record's two encryption values, and any machine:
1. At drive.google.com, download the whole `Backups` folder (names are
   gibberish; that's the encryption). Unzip it, e.g. to `~/restore/Backups`.
2. Install rclone (<https://rclone.org/install/>) and PostgreSQL.
3. `rclone config create local-crypt crypt remote ~/restore/Backups password '<Encryption password>' password2 '<Encryption salt>' --obscure`
4. `rclone ls local-crypt:` shows the real names
   (`postgres/sonofleo_prod/sonofleo_prod-YYYY-MM-DD.dump`), then
   `rclone copy local-crypt:postgres/sonofleo_prod/<file>.dump ~/restore/`
5. `createdb sonofleo_restore && pg_restore --no-owner -d sonofleo_restore ~/restore/<file>.dump`

If the NAS survives, a recent nightly (last 14 days) is in its
`Media/Backups/postgres/sonofleo_prod/` share, unencrypted: skip to step 5.
