"""Structured JSON log lines (one per event, UTC). Callers never pass secrets, prompts or model output."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any


def log(severity: str, event: str, /, **fields: Any) -> None:
    print(json.dumps({"ts": datetime.now(UTC).isoformat(), "severity": severity, "event": event, **fields}), flush=True)
