#!/usr/bin/env python3
"""Upload a file to a Discord channel via bot token + REST API.

Usage:
    discord_upload.py --channel CHANNEL_ID --token-file TOKEN_PATH --file FILE_PATH [--message MSG]
"""

import argparse
import sys
from pathlib import Path

import requests

DISCORD_API = "https://discord.com/api/v10"


def upload(channel_id: str, token: str, file_path: str, message: str = "") -> None:
    url = f"{DISCORD_API}/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {token}"}

    with open(file_path, "rb") as f:
        files = {"file": (Path(file_path).name, f)}
        data = {"content": message} if message else {}
        resp = requests.post(url, headers=headers, files=files, data=data)

    resp.raise_for_status()
    print(f"Uploaded {Path(file_path).name} to channel {channel_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload file to Discord")
    parser.add_argument("--channel", required=True, help="Discord channel ID")
    parser.add_argument("--token-file", required=True, help="Path to bot token file")
    parser.add_argument("--file", required=True, help="Path to file to upload")
    parser.add_argument("--message", default="", help="Optional message with upload")
    args = parser.parse_args()

    token = Path(args.token_file).read_text().strip()
    upload(args.channel, token, args.file, args.message)


if __name__ == "__main__":
    main()
