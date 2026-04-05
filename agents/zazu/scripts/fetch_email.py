#!/home/dan/.openclaw/skills/morning-report/scripts/.venv/bin/python3
"""Fetch overnight Gmail messages via the Gmail API."""

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
PASS_GMAIL_CREDS = "openclaw/zazu/gmail-credentials"
PASS_GMAIL_TOKEN = "openclaw/zazu/gmail-token"


def _pass_show(entry):
    """Read an entry from pass store."""
    return subprocess.check_output(["pass", "show", entry], text=True)


def _pass_insert(entry, content):
    """Write content to pass store."""
    subprocess.run(
        ["pass", "insert", "-m", "-f", entry],
        input=content, text=True, check=True,
    )


def get_credentials():
    creds = None
    try:
        token_json = _pass_show(PASS_GMAIL_TOKEN)
        creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        pass
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds_json = _pass_show(PASS_GMAIL_CREDS)
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                f.write(creds_json)
                tmp_path = f.name
            try:
                flow = InstalledAppFlow.from_client_secrets_file(tmp_path, SCOPES)
                creds = flow.run_local_server(port=0)
            finally:
                os.unlink(tmp_path)
        _pass_insert(PASS_GMAIL_TOKEN, creds.to_json())
    return creds


def fetch_overnight_emails(hours=16):
    creds = get_credentials()
    service = build("gmail", "v1", credentials=creds)

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    query = f"after:{int(since.timestamp())} -category:promotions -category:social"

    results = service.users().messages().list(
        userId="me", q=query, maxResults=50
    ).execute()

    messages = results.get("messages", [])
    if not messages:
        print(json.dumps([]))
        return

    output = []
    for msg_meta in messages:
        msg = service.users().messages().get(
            userId="me", id=msg_meta["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()

        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        output.append({
            "from": headers.get("From", "Unknown"),
            "subject": headers.get("Subject", "(no subject)"),
            "date": headers.get("Date", "Unknown"),
            "snippet": msg.get("snippet", ""),
        })

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 16
    fetch_overnight_emails(hours)
