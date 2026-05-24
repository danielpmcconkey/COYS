#!/usr/bin/env python3
"""Fetch recent messages from a Discord channel via bot token + REST API.

Usage:
    python fetch_discord.py --channel CHANNEL_ID [--limit N] [--before ID] [--after ID]

Returns JSON list of messages with id, timestamp, author, content, attachments,
and embeds. Embeds are preserved (trimmed) so callers can see what auto-rendered
in the client — useful when auditing whether URLs were properly suppressed with
angle brackets.
"""

import argparse
import json
import sys
from pathlib import Path

import requests

DISCORD_API = "https://discord.com/api/v10"
DEFAULT_TOKEN_FILE = "/home/zazu/.discord-token"


def get_token(token_file: str) -> str:
    return Path(token_file).read_text().strip()


def fetch_messages(channel_id, token, limit=50, before="", after=""):
    headers = {"Authorization": f"Bot {token}"}
    params = {"limit": min(max(limit, 1), 100)}
    if before:
        params["before"] = before
    if after:
        params["after"] = after

    resp = requests.get(
        f"{DISCORD_API}/channels/{channel_id}/messages",
        headers=headers,
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _trim_embed(e):
    return {
        "title": e.get("title"),
        "description": (e.get("description") or "")[:200],
        "url": e.get("url"),
        "type": e.get("type"),
        "thumbnail": (e.get("thumbnail") or {}).get("url"),
        "image": (e.get("image") or {}).get("url"),
        "provider": (e.get("provider") or {}).get("name"),
    }


def main():
    parser = argparse.ArgumentParser(description="Fetch Discord channel messages")
    parser.add_argument("--channel", required=True, help="Discord channel ID")
    parser.add_argument(
        "--token-file", default=DEFAULT_TOKEN_FILE,
        help=f"path to plain-text token file (default: {DEFAULT_TOKEN_FILE})",
    )
    parser.add_argument(
        "--limit", type=int, default=50, help="messages to fetch (max 100)",
    )
    parser.add_argument("--before", default="", help="fetch messages before this message ID")
    parser.add_argument("--after", default="", help="fetch messages after this message ID")
    args = parser.parse_args()

    token = get_token(args.token_file)
    messages = fetch_messages(args.channel, token, args.limit, args.before, args.after)

    output = []
    for m in messages:
        output.append({
            "id": m["id"],
            "timestamp": m["timestamp"],
            "author": m["author"]["username"],
            "content": m["content"],
            "attachments": [
                {"url": a.get("url"), "filename": a.get("filename")}
                for a in m.get("attachments", [])
            ],
            "embeds": [_trim_embed(e) for e in m.get("embeds", [])],
        })

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
