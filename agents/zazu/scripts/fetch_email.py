#!/usr/bin/env python3
"""Fetch overnight Gmail messages via the Gmail API."""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
GMAIL_CREDS_FILE = os.path.expanduser("~/.gmail-credentials")
GMAIL_TOKEN_FILE = os.path.expanduser("~/.gmail-token")


def _read_secret(filepath):
    """Read a secret from a plain-text file."""
    with open(filepath) as f:
        return f.read()


def _write_secret(filepath, content):
    """Write content to a secret file (mode 600)."""
    with open(filepath, "w") as f:
        f.write(content)
    os.chmod(filepath, 0o600)


def get_credentials():
    creds = None
    try:
        token_json = _read_secret(GMAIL_TOKEN_FILE)
        creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds_json = _read_secret(GMAIL_CREDS_FILE)
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                f.write(creds_json)
                tmp_path = f.name
            try:
                flow = InstalledAppFlow.from_client_secrets_file(tmp_path, SCOPES)
                creds = flow.run_local_server(port=0)
            finally:
                os.unlink(tmp_path)
        _write_secret(GMAIL_TOKEN_FILE, creds.to_json())
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
