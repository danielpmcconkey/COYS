"""Load agent configuration from YAML."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

COYS_HOME = Path(os.environ.get("COYS_HOME", Path(__file__).resolve().parent.parent))


@dataclass
class DiscordConfig:
    channel_id: str = ""
    token_pass: str = ""  # path in pass store (legacy)
    token_file: str = ""  # path to plain-text token file


@dataclass
class CronConfig:
    schedule: str = ""
    timeout_seconds: int = 600
    prompt: str = ""
    delivery: str = "self"  # self | capture


@dataclass
class AgentConfig:
    name: str = ""
    emoji: str = ""
    mode: str = "cron"  # cron | interactive | dual
    model: str = "sonnet"
    discord: Optional[DiscordConfig] = None
    cron: Optional[CronConfig] = None
    extra_dirs: list[str] = field(default_factory=list)


def load_config(agent_name: str) -> AgentConfig:
    """Load config for a named agent from agents/{name}/config.yaml."""
    config_path = COYS_HOME / "agents" / agent_name / "config.yaml"
    with open(config_path) as f:
        raw = yaml.safe_load(f)

    discord = DiscordConfig(**raw["discord"]) if "discord" in raw else None
    cron = CronConfig(**raw["cron"]) if "cron" in raw else None

    return AgentConfig(
        name=raw.get("name", agent_name),
        emoji=raw.get("emoji", ""),
        mode=raw.get("mode", "cron"),
        model=raw.get("model", "sonnet"),
        discord=discord,
        cron=cron,
        extra_dirs=raw.get("extra_dirs", []),
    )
