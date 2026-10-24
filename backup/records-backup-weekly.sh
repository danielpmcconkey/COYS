#!/usr/bin/env bash
# Weekly: tar.gz of BusinessRecords to the NAS as BusinessRecords-YYYY-MM-DD-HHMM.tar.gz,
# prune to 5 weeks (first of each month kept forever), then mirror the archive folder to the encrypted Drive remote,
# so anything pruned here is deleted from Drive too. Writes .offsite-status.json.
# The newest RECORDS_KEEP_COUNT archives are always kept, so a job that has
# stopped working can't prune away the last good copies.
set -euo pipefail
source "$(dirname "$(readlink -f "$0")")/backup.conf"
exec >>"$LOG_DIR/$(date +%F).log" 2>&1
trap 'echo "$(date -Is) records: FAILED (line $LINENO)"' ERR

echo "$(date -Is) records: start"
for d in "$RECORDS_SRC" "$(dirname "$RECORDS_DEST")"; do
    if [[ ! -d $d ]]; then
        echo "$(date -Is) records: $d not found (NAS not mounted?), refusing"
        exit 1
    fi
done
mkdir -p "$RECORDS_DEST"

# Archive under a .partial name; only named once tar can read it back.
# tar exit 1 means a file changed while being read: the archive is still usable.
out="$RECORDS_DEST/BusinessRecords-$(date +%F-%H%M).tar.gz"
tmp="$out.partial"
rc=0
tar -czf "$tmp" -C "$(dirname "$RECORDS_SRC")" \
    --exclude='@eaDir' --exclude='.DS_Store' \
    "$(basename "$RECORDS_SRC")" || rc=$?
if (( rc > 1 )); then
    echo "$(date -Is) records: tar exited $rc"
    exit 1
fi
(( rc == 0 )) || echo "$(date -Is) records: tar warning, a file changed while being read"
tar -tzf "$tmp" >/dev/null
mv -f "$tmp" "$out"
echo "$(date -Is) records: wrote $out ($(stat -c %s "$out") bytes)"

# Prune: RECORDS_KEEP_DAYS old or older, never the newest RECORDS_KEEP_COUNT,
# never the first archive of a month (those are kept forever)
cutoff=$(date -d "-$RECORDS_KEEP_DAYS days" +%F)
mapfile -t archives < <(find "$RECORDS_DEST" -maxdepth 1 -type f -printf '%f\n' \
    | grep -E '^BusinessRecords-[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{4}\.tar\.gz$' | sort)
eligible=$(( ${#archives[@]} > RECORDS_KEEP_COUNT ? ${#archives[@]} - RECORDS_KEEP_COUNT : 0 ))
declare -A month_seen=()
for f in "${archives[@]:0:eligible}"; do
    d=${f#BusinessRecords-}; d=${d:0:10}
    if [[ -z ${month_seen[${d:0:7}]:-} ]]; then
        month_seen[${d:0:7}]=1
        continue
    fi
    [[ $d > $cutoff ]] && continue
    rm -- "$RECORDS_DEST/$f"
    echo "$(date -Is) records: pruned $f"
done

# Mirror to Drive, so pruned archives go there too. Skip Drive's trash so they're really gone.
rclone sync "$RECORDS_DEST" "$RECORDS_REMOTE" \
    --include 'BusinessRecords-*.tar.gz' --drive-use-trash=false -v
rclone cryptcheck "$RECORDS_DEST" "$RECORDS_REMOTE" --include 'BusinessRecords-*.tar.gz'

count=$(find "$RECORDS_DEST" -maxdepth 1 -type f -name 'BusinessRecords-*.tar.gz' | wc -l)
printf '{"completed_at": "%s", "archives": %d, "latest": "%s"}\n' \
    "$(date -Is)" "$count" "$(basename "$out")" >"$RECORDS_DEST/.offsite-status.json"
echo "$(date -Is) records: done, $count archive(s) here and verified in Drive"
