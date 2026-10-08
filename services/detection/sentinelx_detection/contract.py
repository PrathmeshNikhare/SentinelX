"""Validates Kafka messages against the generated contract (D-042) instead of re-declaring the event shape."""

from __future__ import annotations

import json
from datetime import datetime
from functools import cache
from typing import Any

from jsonschema import Draft202012Validator

from .config import CONTRACTS_DIR
from .models import Event


class ContractError(ValueError):
    """The message is not valid JSON or does not match normalized-event v1. Messages never include payload values."""


@cache
def _validator() -> Draft202012Validator:
    schema = json.loads((CONTRACTS_DIR / "normalized-event.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def parse_message(value: bytes | str | None) -> Event:
    if value is None:
        raise ContractError("empty message")
    try:
        data: Any = json.loads(value)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ContractError("invalid JSON") from error
    errors = sorted(_validator().iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        # Path and failing keyword only: jsonschema messages quote the offending (untrusted) value.
        details = "; ".join(f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.validator}" for e in errors[:10])
        raise ContractError(f"does not match normalized-event v1: {details}")
    return Event(
        event_id=data["event_id"],
        occurred_at=datetime.fromisoformat(data["occurred_at"]),
        user_id=data["user_id"],
        source_ip=data["source_ip"],
        event_type=data["event_type"],
        action=data["action"],
        resource=data["resource"],
        status=data["status"],
        metadata=data["metadata"],
    )
