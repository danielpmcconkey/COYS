#!/usr/bin/env bash
# Weekly: copies first-of-the-month dumps not yet in Drive to the encrypted
# remote, verifies them, then writes .offsite-status.json for Scotty.
# copy, never sync: nothing in Drive is ever deleted by this script.
set -euo pipefail
source "$(dirname "$(readlink -f "$0")")/backup.conf"
exec >>"$LOG_DIR/$(date +%F).log" 2>&1
trap 'echo "$(date -Is) offsite: FAILED (line $LINENO)"' ERR

echo "$(date -Is) offsite: start"
if [[ ! -d $DEST ]]; then
    echo "$(date -Is) offsite: $DEST not found (NAS not mounted?), refusing"
    exit 1
fi

latest=$(find "$DEST" -maxdepth 1 -type f -name "$MONTHLY_GLOB" -printf '%f\n' | sort | tail -n 1)
count=$(find "$DEST" -maxdepth 1 -type f -name "$MONTHLY_GLOB" | wc -l)
if (( count > 0 )); then
    rclone copy "$DEST" "$REMOTE" --include "$MONTHLY_GLOB" -v
    rclone cryptcheck "$DEST" "$REMOTE" --include "$MONTHLY_GLOB" --one-way
fi
printf '{"completed_at": "%s", "monthly_files": %d, "latest": "%s"}\n' \
    "$(date -Is)" "$count" "$latest" >"$DEST/.offsite-status.json"
echo "$(date -Is) offsite: done, $count monthly file(s) verified in Drive, latest '$latest'"
