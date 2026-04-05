#!/usr/bin/env python3
"""OAuth token management for YouTube Data API v3.

First run: launches browser-based OAuth flow, saves refresh token.
Subsequent runs: loads and refreshes the token automatically.

Usage as module:
    from auth import get_youtube_service
    youtube = get_youtube_service()

Usage as CLI:
    python3 auth.py          # Verify/refresh token, print status JSON
    python3 auth.py --init   # Force fresh OAuth flow (browser)
"""

import json
import os
import subprocess
import sys
import tempfile

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

CLIENT_SECRET_FILE = os.path.expanduser("~/.youtube-client-secret")
YOUTUBE_TOKEN_FILE = os.path.expanduser("~/.youtube-token")
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]


def _read_secret(filepath):
    """Read a secret from a plain-text file."""
    with open(filepath) as f:
        return f.read()


def _write_secret(filepath, content):
    """Write content to a secret file (mode 600)."""
    with open(filepath, "w") as f:
        f.write(content)
    os.chmod(filepath, 0o600)


def _load_credentials():
    """Load credentials from token file, or return None."""
    try:
        token_json = _read_secret(YOUTUBE_TOKEN_FILE)
    except FileNotFoundError:
        return None
    creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
    return creds


def _save_credentials(creds):
    """Save credentials to token file."""
    data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
    }
    _write_secret(YOUTUBE_TOKEN_FILE, json.dumps(data, indent=2))


def _run_oauth_flow():
    """Run the browser-based OAuth consent flow."""
    try:
        client_json = _read_secret(CLIENT_SECRET_FILE)
    except FileNotFoundError:
        print(f"ERROR: Client secret not found at {CLIENT_SECRET_FILE}", file=sys.stderr)
        sys.exit(1)
    # InstalledAppFlow needs a file path, so write to a temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(client_json)
        tmp_path = f.name
    try:
        flow = InstalledAppFlow.from_client_secrets_file(tmp_path, SCOPES)
        creds = flow.run_local_server(port=0)
    finally:
        os.unlink(tmp_path)
    _save_credentials(creds)
    print("OAuth flow complete. Token saved.", file=sys.stderr)
    return creds


def get_credentials(force_init=False):
    """Get valid OAuth credentials. Refreshes or runs flow as needed."""
    if force_init:
        return _run_oauth_flow()

    creds = _load_credentials()

    if creds is None:
        print("No token found. Running OAuth flow...", file=sys.stderr)
        return _run_oauth_flow()

    if creds.valid:
        return creds

    if creds.expired and creds.refresh_token:
        print("Token expired. Refreshing...", file=sys.stderr)
        creds.refresh(Request())
        _save_credentials(creds)
        print("Token refreshed.", file=sys.stderr)
        return creds

    # Token exists but can't be refreshed — re-auth
    print("Token invalid and not refreshable. Running OAuth flow...", file=sys.stderr)
    return _run_oauth_flow()


def get_youtube_service(force_init=False):
    """Return an authenticated YouTube Data API v3 service client."""
    creds = get_credentials(force_init=force_init)
    return build("youtube", "v3", credentials=creds)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Marcus YouTube OAuth manager")
    parser.add_argument("--init", action="store_true",
                        help="Force fresh OAuth flow (opens browser)")
    args = parser.parse_args()

    creds = get_credentials(force_init=args.init)
    status = {
        "valid": creds.valid,
        "expired": creds.expired,
        "has_refresh_token": creds.refresh_token is not None,
        "token_store": YOUTUBE_TOKEN_FILE,
    }
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
