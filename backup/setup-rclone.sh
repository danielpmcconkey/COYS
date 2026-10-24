#!/usr/bin/env bash
# One-time: connect rclone to Google Drive, with an encrypted remote on top.
#   bash /media/dan/fdrive/codeprojects/COYS/backup/setup-rclone.sh
# Run as dan, in your own terminal, NOT through Claude's "!" prefix: you'll
# be typing secrets, and anything run through "!" lands in the transcript.
set -euo pipefail
[[ $EUID -ne 0 ]] || { echo "Run as dan, not root." >&2; exit 1; }
source "$(dirname "$(readlink -f "$0")")/backup.conf"

if rclone listremotes | grep -qx 'gdrive:'; then
    echo "gdrive: already configured, skipping"
else
    echo "Own Google OAuth client? Press Enter twice to use rclone's built-in one."
    read -rp  "Google OAuth client ID: " cid
    read -rsp "Google OAuth client secret: " csecret; echo
    client=()
    [[ -n $cid ]] && client=(client_id "$cid" client_secret "$csecret")
    echo "A browser window opens next: sign in and allow access."
    rclone config create gdrive drive "${client[@]}" scope drive.file
fi

if rclone listremotes | grep -qx 'gdrive-crypt:'; then
    echo "gdrive-crypt: already configured, skipping"
else
    read -rsp "Encryption password (paste from Keeper): " p1; echo
    read -rsp "Encryption salt (paste from Keeper): " p2; echo
    [[ -n $p1 && -n $p2 && $p1 != "$p2" ]] || { echo "Need two different, non-empty values." >&2; exit 1; }
    rclone config create gdrive-crypt crypt remote gdrive:Backups \
        password "$p1" password2 "$p2" --obscure >/dev/null
    unset p1 p2
fi
chmod 600 "$(rclone config file | tail -n 1)"

echo "== round trip"
echo "connection test $(date -Is)" | rclone rcat "$REMOTE/.connection-test"
rclone cat "$REMOTE/.connection-test"
echo "== what Google sees (should be gibberish names):"
rclone lsf -R gdrive:Backups
echo
echo "Done. The first off-site run is Sunday 04:30; to run it now:"
echo "  $(dirname "$(readlink -f "$0")")/pg-backup-offsite.sh"
