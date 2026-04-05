"""Logging setup for COYS agents."""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

COYS_HOME = Path(os.environ.get("COYS_HOME", Path(__file__).resolve().parent.parent))
LOG_DIR = COYS_HOME / "logs"


def setup(agent_name: str) -> logging.Logger:
    """Create a logger that writes to logs/{agent}/{date}.log and stderr."""
    agent_dir = LOG_DIR / agent_name
    agent_dir.mkdir(parents=True, exist_ok=True)

    log_file = agent_dir / f"{datetime.now(timezone.utc):%Y-%m-%d}.log"

    logger = logging.getLogger(f"coys.{agent_name}")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")

        fh = logging.FileHandler(log_file)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)

    return logger
