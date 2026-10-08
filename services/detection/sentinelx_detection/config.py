"""Paths and environment for the detection service. The single .env lives at the repo root."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVICE_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = REPO_ROOT / "contracts" / "v1"
FIXTURES_DIR = REPO_ROOT / "fixtures"
DEFAULT_MODEL_PATH = SERVICE_ROOT / "models" / "iforest-v1.joblib"

DEFAULT_TOPIC = "security-events"
DEFAULT_GROUP_ID = "sentinelx-detection"


def load_root_env(path: Path = REPO_ROOT / ".env") -> None:
    """Loads KEY=VALUE lines from the repo-root .env. Variables already in the environment take precedence."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def require_env(name: str) -> str:
    load_root_env()
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"{name} is not set (copy .env.example to .env at the repo root)")
    return value


def optional_env(name: str, default: str) -> str:
    load_root_env()
    return os.environ.get(name) or default
