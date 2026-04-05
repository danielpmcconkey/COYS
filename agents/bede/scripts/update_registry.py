#!/usr/bin/env python3
"""Update the transcript registry with a new entry.

Usage: update_registry.py '<json entry>'

Appends the entry to registry.json, with dedup protection.
"""

import json
import sys

REGISTRY_PATH = (
    "/media/dan/fdrive/codeprojects/ai-dev-playbook"
    "/TranscriptSummaries/registry.json"
)


def update(entry_json):
    entry = json.loads(entry_json)

    try:
        with open(REGISTRY_PATH) as f:
            registry = json.load(f)
    except FileNotFoundError:
        registry = []

    # Dedup check
    existing_ids = {e["session_id"] for e in registry}
    if entry["session_id"] in existing_ids:
        print(json.dumps({
            "status": "skipped",
            "reason": "already in registry",
            "session_id": entry["session_id"],
        }))
        return

    registry.append(entry)

    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2)
        f.write("\n")

    print(json.dumps({
        "status": "added",
        "session_id": entry["session_id"],
        "registry_count": len(registry),
    }))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({
            "status": "error",
            "reason": "Usage: update_registry.py '<json entry>'",
        }))
        sys.exit(1)
    update(sys.argv[1])
