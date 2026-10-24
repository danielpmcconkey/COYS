#!/usr/bin/env bash
# Deletes dated dumps older than KEEP_DAYS, never a first-of-the-month one.
# The newest KEEP_DAYS dumps are always kept, so a nightly that has stopped
# working can't leave the prune eating the last good copies.
# DRY_RUN=1 logs what would go and deletes nothing.
set -euo pipefail
source "$(dirname "$(readlink -f "$0")")/backup.conf"
exec >>"$LOG_DIR/$(date +%F).log" 2>&1
trap 'echo "$(date -Is) prune: FAILED (line $LINENO)"' ERR

if [[ ! -d $DEST ]]; then
    echo "$(date -Is) prune: $DEST not found (NAS not mounted?), refusing"
    exit 1
fi

cutoff=$(date -d "-$KEEP_DAYS days" +%F)
mapfile -t dumps < <(find "$DEST" -maxdepth 1 -type f -printf '%f\n' \
    | grep -E "^$DB-[0-9]{4}-[0-9]{2}-[0-9]{2}\.dump$" | sort)
eligible=$(( ${#dumps[@]} > KEEP_DAYS ? ${#dumps[@]} - KEEP_DAYS : 0 ))

deleted=0
for f in "${dumps[@]:0:eligible}"; do
    d=${f#"$DB-"}; d=${d%.dump}
    [[ $d == *-01 ]] && continue
    [[ $d < $cutoff ]] || continue
    if [[ ${DRY_RUN:-} ]]; then
        echo "$(date -Is) prune: would delete $f (DRY_RUN)"
    else
        rm -- "$DEST/$f"
        echo "$(date -Is) prune: deleted $f"
    fi
    deleted=$((deleted + 1))
done
echo "$(date -Is) prune: done, $deleted deleted, ${#dumps[@]} were present"
