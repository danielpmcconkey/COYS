#!/usr/bin/env python3
"""Post a message to Discord via bot token + REST API.

Usage:
    python discord_post.py --channel CHANNEL_ID --token-pass PASS_PATH "message"
    echo "message" | python discord_post.py --channel CHANNEL_ID --token-pass PASS_PATH

Handles chunking for Discord's 2000 character limit.
"""

import argparse
import subprocess
import sys
from pathlib import Path

import requests

DISCORD_API = "https://discord.com/api/v10"
MAX_LENGTH = 2000


def get_token(pass_path: str = "", token_file: str = "") -> str:
    """Read a bot token from a file or the pass store."""
    if token_file:
        return Path(token_file).read_text().strip()
    return subprocess.check_output(
        ["pass", "show", pass_path], text=True
    ).strip()


def post_message(channel_id: str, token: str, content: str) -> None:
    """Post content to a Discord channel, chunking if necessary."""
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
    }

    chunks = _chunk(content)
    for chunk in chunks:
        resp = requests.post(
            f"{DISCORD_API}/channels/{channel_id}/messages",
            headers=headers,
            json={"content": chunk},
        )
        resp.raise_for_status()


def _chunk(text: str) -> list[str]:
    """Split text into chunks that fit Discord's message limit."""
    pieces = []
    while text:
        if len(text) <= MAX_LENGTH:
            pieces.append(text)
            break
        split = text.rfind("\n", 0, MAX_LENGTH)
        if split == -1:
            split = MAX_LENGTH
        pieces.append(text[:split])
        text = text[split:].lstrip("\n")
    return pieces


def main():
    parser = argparse.ArgumentParser(description="Post to Discord")
    parser.add_argument("--channel", required=True, help="Discord channel ID")
    token_group = parser.add_mutually_exclusive_group(required=True)
    token_group.add_argument("--token-pass", help="pass store path for bot token")
    token_group.add_argument("--token-file", help="path to plain-text token file")
    parser.add_argument(
        "message", nargs="?", help="Message (or pipe via stdin)"
    )
    args = parser.parse_args()

    message = args.message
    if not message and not sys.stdin.isatty():
        message = sys.stdin.read()
    if not message:
        print("No message provided", file=sys.stderr)
        sys.exit(1)

    token = get_token(args.token_pass or "", args.token_file or "")
    post_message(args.channel, token, message)


if __name__ == "__main__":
    main()
