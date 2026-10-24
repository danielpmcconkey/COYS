#!/usr/bin/env bash
# One-time root setup for the sonofleo_prod backup routine. Safe to re-run.
#   sudo bash /media/dan/fdrive/codeprojects/COYS/backup/setup-root.sh
# Run it in your own terminal: nothing secret is printed, but sudo wants a prompt.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Run with sudo." >&2; exit 1; }

HERE=$(dirname "$(readlink -f "$0")")
source "$HERE/backup.conf"
USER_NAME=dan
PGPASS=/home/$USER_NAME/.pgpass
CRON=/etc/cron.d/coys
OLD_LEOBLOOM=/mnt/media/BusinessRecords/LeoBloomOps/Backups
as_dan() { sudo -u "$USER_NAME" "$@"; }

echo "== 1. rclone"
if command -v rclone >/dev/null; then
    echo "already installed: $(rclone version | head -n 1)"
else
    curl -fsSL https://rclone.org/install.sh | bash
fi

echo "== 2. read-only role $ROLE, password into $PGPASS"
if sudo -u postgres psql -Atc "select 1 from pg_roles where rolname = '$ROLE'" | grep -q 1; then
    echo "role exists, leaving it and $PGPASS alone"
else
    pw=$(openssl rand -hex 24)
    sudo -u postgres psql -v ON_ERROR_STOP=1 -q <<SQL
CREATE ROLE $ROLE LOGIN PASSWORD '$pw';
GRANT pg_read_all_data TO $ROLE;
GRANT CONNECT ON DATABASE $DB TO $ROLE;
SQL
    as_dan touch "$PGPASS"
    chmod 600 "$PGPASS"
    echo "localhost:5432:$DB:$ROLE:$pw" >>"$PGPASS"
    unset pw
    echo "role created"
fi

echo "== 3. directories"
as_dan mkdir -p "$DEST" /mnt/media/Backups/postgres/leobloom_prod
install -d -o "$USER_NAME" -g coys -m 2775 "$LOG_DIR"
if compgen -G "$OLD_LEOBLOOM/leobloom_prod-*" >/dev/null; then
    as_dan mv -n "$OLD_LEOBLOOM"/leobloom_prod-* /mnt/media/Backups/postgres/leobloom_prod/
    echo "moved the LeoBloom final dump to /mnt/media/Backups/postgres/leobloom_prod/"
fi
chmod 755 "$HERE"/pg-backup-*.sh

echo "== 4. cron"
if grep -q pg-backup- "$CRON"; then
    echo "already in $CRON"
else
    cat >>"$CRON" <<'EOF'

# Postgres backup (sonofleo_prod): nightly dump 03:15, prune 03:45, off-site Sundays 04:30 ET
15 3 * * * dan $COYS_HOME/backup/pg-backup-nightly.sh
45 3 * * * dan $COYS_HOME/backup/pg-backup-prune.sh
30 4 * * 0 dan $COYS_HOME/backup/pg-backup-offsite.sh
EOF
    echo "added to $CRON"
fi

echo "== 5. first dump, as $USER_NAME"
as_dan "$HERE/pg-backup-nightly.sh" || { tail -n 5 "$LOG_DIR/$(date +%F).log"; exit 1; }
ls -l "$DEST"
echo
echo "Done. Next: setup-rclone.sh as yourself (no sudo), in your own terminal."
