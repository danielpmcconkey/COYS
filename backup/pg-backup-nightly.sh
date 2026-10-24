#!/usr/bin/env bash
# Nightly dump of sonofleo_prod to the NAS as <db>-YYYY-MM-DD.dump.
# Written under a .partial name and only renamed once pg_restore can read it back.
set -euo pipefail
source "$(dirname "$(readlink -f "$0")")/backup.conf"
exec >>"$LOG_DIR/$(date +%F).log" 2>&1
trap 'echo "$(date -Is) nightly: FAILED (line $LINENO)"' ERR

echo "$(date -Is) nightly: start"
if [[ ! -d $DEST ]]; then
    echo "$(date -Is) nightly: $DEST not found (NAS not mounted?), refusing"
    exit 1
fi

out="$DEST/$DB-$(date +%F).dump"
tmp="$out.partial"
pg_dump -h localhost -U "$ROLE" -d "$DB" --no-password -Fc -Z 9 -f "$tmp"
pg_restore --list "$tmp" >/dev/null
mv -f "$tmp" "$out"
echo "$(date -Is) nightly: wrote $out ($(stat -c %s "$out") bytes)"
