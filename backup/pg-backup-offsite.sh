#!/usr/bin/env bash
# Nightly, after the dump and prune: puts the dump folder (14 dailies plus
# every first-of-the-month dump) on the encrypted remote, verifies it, then
# writes .offsite-status.json for Scotty.
# Monthlies: copy only, never deleted or overwritten in Drive.
# Dailies: sync, so one the prune deleted here goes from Drive too (no trash),
# but never overwritten, and at most 2 deletions a night, so a wiped or
# encrypted NAS fails the job instead of emptying Drive.
set -euo pipefail
source "$(dirname "$(readlink -f "$0")")/backup.conf"
exec >>"$LOG_DIR/$(date +%F).log" 2>&1
trap 'echo "$(date -Is) offsite: FAILED (line $LINENO)"' ERR

echo "$(date -Is) offsite: start"
if [[ ! -d $DEST ]]; then
    echo "$(date -Is) offsite: $DEST not found (NAS not mounted?), refusing"
    exit 1
fi

# An empty folder here would empty Drive too
latest=$(find "$DEST" -maxdepth 1 -type f -name "$DUMP_GLOB" -printf '%f\n' | sort | tail -n 1)
count=$(find "$DEST" -maxdepth 1 -type f -name "$DUMP_GLOB" | wc -l)
if (( count == 0 )); then
    echo "$(date -Is) offsite: no dumps in $DEST, refusing to sync"
    exit 1
fi

rclone copy "$DEST" "$REMOTE" --include "$MONTHLY_GLOB" --immutable -v
rclone sync "$DEST" "$REMOTE" --filter "- $MONTHLY_GLOB" --filter "+ $DUMP_GLOB" --filter "- *" \
    --immutable --max-delete 2 --drive-use-trash=false -v
rclone cryptcheck "$DEST" "$REMOTE" --include "$DUMP_GLOB" --one-way
printf '{"completed_at": "%s", "dumps": %d, "latest": "%s"}\n' \
    "$(date -Is)" "$count" "$latest" >"$DEST/.offsite-status.json"
echo "$(date -Is) offsite: done, $count dump(s) verified in Drive, latest '$latest'"
