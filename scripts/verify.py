"""SentinelX verification entrypoint (D-024).

Standard library only, so it runs before any venv or node_modules exists.
Usage (from anywhere): python scripts/verify.py
Exit code 0 only when no check FAILs. WARN does not fail the run.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INFRA_SERVICES = ("postgres", "kafka", "qdrant")
PYTHON_SERVICES = ("services/detection", "services/ai")
KAFKA_TOPIC = "security-events"
QDRANT_READY_URL = "http://localhost:6333/readyz"
POSTGRES_SSL_REQUEST = struct.pack("!ii", 8, 80877103)

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"


@dataclass(frozen=True)
class Result:
    name: str
    status: str
    detail: str = ""


# ---------- pure helpers (covered by scripts/test_verify.py) ----------


def compose_variables(compose_text: str) -> set[str]:
    """Names of ${VAR...} interpolations in a Compose file ($$VAR is an escape, not a reference)."""
    return set(re.findall(r"(?<!\$)\$\{([A-Za-z_][A-Za-z0-9_]*)", compose_text))


def env_example_keys(env_text: str) -> set[str]:
    keys = set()
    for line in env_text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            keys.add(line.split("=", 1)[0].strip())
    return keys


def forbidden_tracked_paths(tracked: list[str]) -> list[str]:
    """Tracked paths that must never be committed: real env files and dependency dirs."""
    env_file = re.compile(r"(^|/)\.env(\.[^/]+)?$")
    bad = []
    for path in tracked:
        if env_file.search(path) and not path.endswith(".env.example"):
            bad.append(path)
        elif re.search(r"(^|/)(node_modules|\.venv)/", path):
            bad.append(path)
    return bad


def parse_compose_ps(output: str) -> dict[str, str]:
    """Map service -> health from `docker compose ps --format json` (JSON array or JSON lines)."""
    output = output.strip()
    if not output:
        return {}
    if output.startswith("["):
        rows = json.loads(output)
    else:
        rows = [json.loads(line) for line in output.splitlines() if line.strip()]
    return {row["Service"]: (row.get("Health") or row.get("State") or "") for row in rows}


# ---------- process helpers ----------


def run(cmd: list[str], cwd: Path = ROOT, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    exe = shutil.which(cmd[0]) or cmd[0]  # resolves npm.cmd on Windows
    return subprocess.run([exe, *cmd[1:]], cwd=cwd, capture_output=True, text=True, timeout=timeout)


def tail(proc: subprocess.CompletedProcess[str], lines: int = 6) -> str:
    text = (proc.stdout + proc.stderr).strip().splitlines()
    return " | ".join(text[-lines:])


def command_check(name: str, cmd: list[str], cwd: Path = ROOT) -> Result:
    try:
        proc = run(cmd, cwd=cwd)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Result(name, FAIL, str(exc))
    return Result(name, PASS) if proc.returncode == 0 else Result(name, FAIL, tail(proc))


def host_port(service: str, container_port: int) -> tuple[str, int] | None:
    proc = run(["docker", "compose", "port", service, str(container_port)])
    if proc.returncode != 0 or ":" not in proc.stdout:
        return None
    host, port = proc.stdout.strip().rsplit(":", 1)
    return ("localhost" if host in ("0.0.0.0", "127.0.0.1") else host), int(port)


# ---------- checks ----------


def check_self_test() -> Result:
    return command_check("verify.py self-test", [sys.executable, "-m", "unittest", "-q", "scripts.test_verify"])


def check_env_file() -> Result:
    if (ROOT / ".env").is_file():
        return Result(".env present", PASS)
    return Result(".env present", FAIL, "copy .env.example to .env")


def check_env_example_covers_compose() -> Result:
    needed = compose_variables((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    missing = needed - env_example_keys((ROOT / ".env.example").read_text(encoding="utf-8"))
    if missing:
        return Result(".env.example covers compose vars", FAIL, "missing: " + ", ".join(sorted(missing)))
    return Result(".env.example covers compose vars", PASS, f"{len(needed)} vars")


def check_git_hygiene() -> Result:
    proc = run(["git", "ls-files"])
    if proc.returncode != 0:
        return Result("git: no secrets/deps tracked", FAIL, tail(proc))
    bad = forbidden_tracked_paths(proc.stdout.splitlines())
    if bad:
        return Result("git: no secrets/deps tracked", FAIL, ", ".join(bad[:5]))
    return Result("git: no secrets/deps tracked", PASS)


def check_compose_config() -> Result:
    return command_check("docker compose config", ["docker", "compose", "config", "--quiet"])


def check_infra_health() -> Result:
    proc = run(["docker", "compose", "ps", "--format", "json"])
    if proc.returncode != 0:
        return Result("infra containers healthy", FAIL, tail(proc))
    health = parse_compose_ps(proc.stdout)
    unhealthy = [f"{svc}={health.get(svc, 'not running')}" for svc in INFRA_SERVICES if health.get(svc) != "healthy"]
    if unhealthy:
        return Result("infra containers healthy", FAIL, ", ".join(unhealthy))
    return Result("infra containers healthy", PASS, ", ".join(INFRA_SERVICES))


def check_postgres() -> Result:
    name = "postgres: host port + credentials"
    address = host_port("postgres", 5432)
    if address is None:
        return Result(name, FAIL, "postgres port not published (is the stack up?)")
    # Host side: the published port must answer the PostgreSQL SSLRequest with 'S' or 'N'.
    try:
        with socket.create_connection(address, timeout=5) as sock:
            sock.sendall(POSTGRES_SSL_REQUEST)
            reply = sock.recv(1)
    except OSError as exc:
        return Result(name, FAIL, f"{address[0]}:{address[1]} {exc}")
    if reply not in (b"S", b"N"):
        return Result(name, FAIL, f"{address[1]} is not PostgreSQL (reply {reply!r})")
    # Credentials: connect over the container network address so pg_hba enforces the password.
    # Stdlib has no PostgreSQL client. A host-side password login is covered by the `web: db integration`
    # check (node-postgres connects to the published port with DATABASE_URL credentials).
    login = (
        'PGPASSWORD="$POSTGRES_PASSWORD" psql -h postgres -U "$POSTGRES_USER" '
        '-d "$POSTGRES_DB" -tAc "select 1"'
    )
    proc = run(["docker", "compose", "exec", "-T", "postgres", "sh", "-c", login], timeout=30)
    if proc.returncode != 0 or proc.stdout.strip() != "1":
        return Result(name, FAIL, "password login failed: " + tail(proc))
    return Result(name, PASS, f"localhost:{address[1]}")


def check_kafka() -> Result:
    name = f"kafka: host port + topic {KAFKA_TOPIC}"
    address = host_port("kafka", 9092)
    if address is None:
        return Result(name, FAIL, "kafka port not published (is the stack up?)")
    try:
        socket.create_connection(address, timeout=5).close()
    except OSError as exc:
        return Result(name, FAIL, f"{address[0]}:{address[1]} {exc}")
    # Lists topics through the broker's HOST listener from inside the container. A real host-side produce/consume
    # round trip is covered by the `web: kafka integration` check (Phase 03).
    proc = run(
        ["docker", "compose", "exec", "-T", "kafka", "/opt/kafka/bin/kafka-topics.sh",
         "--bootstrap-server", "localhost:9092", "--list"],
        timeout=60,
    )
    if proc.returncode != 0:
        return Result(name, FAIL, tail(proc))
    if KAFKA_TOPIC not in proc.stdout.split():
        return Result(name, FAIL, f"topic missing; topics: {proc.stdout.split()}")
    return Result(name, PASS, f"localhost:{address[1]}")


def http_status(url: str) -> int | None:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return int(response.status)
    except OSError:
        return None


def check_qdrant() -> Result:
    status = http_status(QDRANT_READY_URL)
    return Result("qdrant /readyz", PASS if status == 200 else FAIL, f"HTTP {status}")


def check_ollama() -> Result:
    # Required from Phase 06 (the AI service). The configured model is checked by the AI service's live test.
    url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/") + "/api/tags"
    status = http_status(url)
    return Result("ollama reachable", PASS if status == 200 else FAIL, f"{url} HTTP {status}")


def check_schema_drift(web: Path) -> Result:
    """schema.ts must match the committed migrations: drizzle-kit generate on a scratch copy must add nothing."""
    name = "web: schema matches migrations"
    scratch = web / ".drift-check"  # relative: drizzle-kit resolves --out against cwd even if absolute
    shutil.rmtree(scratch, ignore_errors=True)
    try:
        shutil.copytree(web / "drizzle", scratch / "drizzle")
        before = set(os.listdir(scratch / "drizzle"))
        proc = run(
            ["npx", "drizzle-kit", "generate", "--dialect=postgresql",
             "--schema=./src/db/schema.ts", "--out=./.drift-check/drizzle"],
            cwd=web,
        )
        if proc.returncode != 0:
            return Result(name, FAIL, tail(proc))
        added = sorted(set(os.listdir(scratch / "drizzle")) - before)
        if added:
            return Result(name, FAIL, f"schema.ts changed without a migration (run `npm run db:generate`): {added}")
        return Result(name, PASS)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def check_web() -> list[Result]:
    web = ROOT / "apps" / "web"
    if not (web / "node_modules").is_dir():
        return [Result("web: toolchain", FAIL, "run `npm ci` in apps/web")]
    return [
        command_check("web: tsc --noEmit", ["npm", "run", "--silent", "typecheck"], cwd=web),
        command_check("web: eslint", ["npm", "run", "--silent", "lint"], cwd=web),
        command_check("web: vitest unit", ["npm", "test", "--silent"], cwd=web),
        check_schema_drift(web),
        # Throwaway database: clean migration, CRUD/constraints, seeds, role permissions (Phase 01).
        command_check("web: db integration", ["npm", "run", "--silent", "test:db"], cwd=web),
        # Host-side produce/consume through the real producer on an isolated test topic (Phase 03).
        command_check("web: kafka integration", ["npm", "run", "--silent", "test:kafka"], cwd=web),
        # Production build + Playwright on ports 3100/3101 with a throwaway sentinelx_e2e database (Phase 02, D-037).
        # Needs `npx playwright install chromium` once.
        command_check("web: e2e (build + playwright)", ["npm", "run", "--silent", "test:e2e"], cwd=web),
    ]


def venv_python(service: Path) -> Path:
    windows = service / ".venv" / "Scripts" / "python.exe"
    return windows if windows.exists() else service / ".venv" / "bin" / "python"


def check_python_service(rel: str) -> list[Result]:
    service = ROOT / rel
    python = venv_python(service)
    label = rel.split("/")[-1]
    if not python.exists():
        return [Result(f"{label}: toolchain", FAIL, f"create {rel}/.venv and install requirements-dev.txt")]
    py = str(python)
    return [
        command_check(f"{label}: ruff", [py, "-m", "ruff", "check", "."], cwd=service),
        command_check(f"{label}: mypy", [py, "-m", "mypy"], cwd=service),
        command_check(f"{label}: pytest", [py, "-m", "pytest", "-q"], cwd=service),
    ]


def main() -> int:
    results: list[Result] = [
        check_self_test(),
        check_env_file(),
        check_env_example_covers_compose(),
        check_git_hygiene(),
        check_compose_config(),
        check_infra_health(),
        check_postgres(),
        check_kafka(),
        check_qdrant(),
        check_ollama(),
        *check_web(),
    ]
    for rel in PYTHON_SERVICES:
        results.extend(check_python_service(rel))

    width = max(len(r.name) for r in results)
    for r in results:
        print(f"[{r.status}] {r.name.ljust(width)}  {r.detail}".rstrip())
    failed = sum(r.status == FAIL for r in results)
    warned = sum(r.status == WARN for r in results)
    print(f"\n{len(results)} checks: {failed} failed, {warned} warnings")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
