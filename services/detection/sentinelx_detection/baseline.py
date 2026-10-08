"""Seeded synthetic baseline of normal activity for Isolation Forest training (D-049). Deterministic for a seed."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np

from .config import FIXTURES_DIR
from .context import Reputation
from .models import Event


@dataclass(frozen=True)
class BaselineConfig:
    seed: int = 42
    users: int = 40
    days: int = 21
    start: str = "2026-06-01T00:00:00+00:00"  # a Monday


DEFAULT_BASELINE = BaselineConfig()


def reputation_from_fixture() -> dict[str, Reputation]:
    """The same data `npm run db:seed` writes to ip_reputation (D-020)."""
    data = json.loads((FIXTURES_DIR / "ip_reputation.json").read_text(encoding="utf-8"))
    return {e["ip"]: Reputation(level=e["reputation"], score=int(e["score"])) for e in data["entries"]}


SHARED_FILES = (
    "\\\\fs01\\shared\\handbook.pdf",
    "\\\\fs01\\shared\\templates\\report.docx",
    "\\\\fs01\\shared\\calendar.xlsx",
)
DEPARTMENTS = ("engineering", "sales", "marketing", "operations", "finance")
ADMIN_COMMANDS = ("msiexec.exe /i agent-update.msi /qn", "cmd.exe /c ipconfig /all", "sc.exe query spooler")


def baseline_events(config: BaselineConfig = DEFAULT_BASELINE) -> list[Event]:
    rng = np.random.default_rng(config.seed)
    start = datetime.fromisoformat(config.start).astimezone(UTC)
    corporate = ["10.10.1.20", "10.10.1.21", "10.10.2.50"] + [f"10.10.{3 + i // 20}.{10 + i % 20}" for i in range(40)]
    events: list[Event] = []

    def add(
        user: str,
        at: datetime,
        ip: str,
        event_type: str,
        action: str,
        resource: str,
        status: str,
        **meta: object,
    ) -> None:
        events.append(Event(f"base-{len(events)}", at, user, ip, event_type, action, resource, status, dict(meta)))

    for u in range(config.users):
        user = f"user{u:02d}"
        is_admin = u < 5
        department = DEPARTMENTS[u % len(DEPARTMENTS)]
        # Corporate machines: often on a known_good address, otherwise an internal address not in ip_reputation.
        home_ips = [
            corporate[int(rng.integers(3))] if rng.random() < 0.4 else corporate[int(rng.integers(len(corporate)))]
            for _ in range(2)
        ]
        for day in range(config.days):
            date = start + timedelta(days=day)
            weekend = date.weekday() >= 5
            if rng.random() > (0.1 if weekend else 0.95):
                continue
            sessions = 1 + int(rng.random() < 0.3)
            for session in range(sessions):
                hour = float(np.clip(rng.normal(9.0 if session == 0 else 14.0, 1.0), 7.0, 17.5))
                t = date + timedelta(hours=hour)
                ip = home_ips[int(rng.random() < 0.2)]
                if rng.random() < 0.03:
                    add(user, t, ip, "authentication", "login", "vpn-portal", "failed", auth_method="password")
                    t += timedelta(seconds=int(rng.integers(20, 90)))
                add(
                    user,
                    t,
                    ip,
                    "authentication",
                    "login",
                    "vpn-portal",
                    "success",
                    auth_method="password+mfa",
                    mfa=True,
                )
                for _ in range(int(rng.integers(3, 12))):
                    t += timedelta(seconds=int(rng.integers(30, 900)))
                    if rng.random() < 0.5:
                        resource = SHARED_FILES[int(rng.integers(len(SHARED_FILES)))]
                    else:
                        resource = f"\\\\fs01\\{department}\\docs\\doc-{int(rng.integers(1, 200))}.pdf"
                    label = "internal" if rng.random() < 0.1 else "public"
                    add(user, t, ip, "file_access", "read", resource, "success", sensitivity=label)
                if is_admin and rng.random() < 0.25:
                    t += timedelta(seconds=int(rng.integers(60, 600)))
                    command = ADMIN_COMMANDS[int(rng.integers(len(ADMIN_COMMANDS)))]
                    add(
                        user,
                        t,
                        ip,
                        "process",
                        "execute",
                        command.split(" ")[0],
                        "success",
                        command_line=command,
                    )
                if is_admin and rng.random() < 0.05:
                    t += timedelta(seconds=int(rng.integers(60, 600)))
                    add(
                        user,
                        t,
                        ip,
                        "process",
                        "execute",
                        "powershell.exe",
                        "success",
                        command_line="powershell.exe Get-Service",
                    )
                t += timedelta(seconds=int(rng.integers(600, 3600)))
                add(user, t, ip, "authentication", "logout", "vpn-portal", "success")
    events.sort(key=lambda e: (e.occurred_at, e.event_id))
    return events
