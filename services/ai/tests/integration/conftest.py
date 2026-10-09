"""Shared fixtures for integration tests: a throwaway database per test module.

Each database is migrated and seeded by the Drizzle tooling (the only DDL source, D-010); `db:roles` enables LOGIN for
the app, tools and writer roles (D-061, D-065). Leftovers from killed runs are swept after an hour.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from psycopg import sql

from sentinelx_ai.config import REPO_ROOT, load_root_env

DB_PREFIX = "sentinelx_ai_test_"
STALE_AFTER_SECONDS = 3600


@dataclass(frozen=True)
class Stack:
    owner_url: str
    app_url: str
    tools_url: str
    writer_url: str


def env(name: str) -> str:
    load_root_env()
    value = os.environ.get(name, "")
    assert value, f"{name} must be set in the repo-root .env (see .env.example)"
    return value


def with_database(url: str, database: str) -> str:
    return urlunsplit(urlsplit(url)._replace(path=f"/{database}"))


def owner_connect(url: str) -> psycopg.Connection[Any]:
    extra: dict[str, Any] = {"connect_timeout": 10}
    if urlsplit(url).hostname == "localhost":
        extra["hostaddr"] = "127.0.0.1"  # D-051
    return psycopg.connect(url, autocommit=True, **extra)


def npm(script: str, overrides: dict[str, str]) -> None:
    executable = shutil.which("npm")
    assert executable, "npm is required: Drizzle migrations are the only DDL source"
    subprocess.run(  # noqa: S603 - fixed argv, no shell
        [executable, "run", "--silent", script],
        cwd=REPO_ROOT / "apps" / "web",
        env={**os.environ, **overrides},
        check=True,
        capture_output=True,
        timeout=180,
    )


def sweep_stale(owner: str) -> None:
    with owner_connect(owner) as conn:
        for (name,) in conn.execute(
            "SELECT datname FROM pg_database WHERE datname LIKE %s", (f"{DB_PREFIX}%",)
        ).fetchall():
            stamp = name.rsplit("_", 1)[-1]
            if stamp.isdigit() and time.time() - int(stamp) > STALE_AFTER_SECONDS:
                conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture(scope="module")
def database(request: pytest.FixtureRequest) -> Iterator[Stack]:
    owner = env("DATABASE_URL")
    module = request.module.__name__.rsplit(".", 1)[-1].removeprefix("test_")[:20]
    name = f"{DB_PREFIX}{module}_{os.getpid()}_{int(time.time())}"
    sweep_stale(owner)
    with owner_connect(owner) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    stack = Stack(
        with_database(owner, name),
        with_database(env("APP_DATABASE_URL"), name),
        with_database(env("AI_TOOLS_DATABASE_URL"), name),
        with_database(env("AI_WRITER_DATABASE_URL"), name),
    )
    try:
        overrides = {
            "DATABASE_URL": stack.owner_url,
            "APP_DATABASE_URL": stack.app_url,
            "AI_TOOLS_DATABASE_URL": stack.tools_url,
            "AI_WRITER_DATABASE_URL": stack.writer_url,
        }
        for script in ("db:migrate", "db:seed", "db:roles"):
            npm(script, overrides)
        yield stack
    finally:
        with owner_connect(owner) as conn:
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
