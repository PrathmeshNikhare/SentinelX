# services/detection

Owner: Detection Engineer (docs/19_AGENT_OWNERSHIP.md)

Detection worker (D-013, D-046):
1. consumes `security-events`;
2. validates each message against `contracts/v1/normalized-event.schema.json`;
3. persists events idempotently;
4. runs deterministic rules, the Isolation Forest anomaly signal and the deterministic risk engine;
5. persists `detection_signals`;
6. writes an alert when risk ≥ 40 (D-052) and correlates events into per-user incidents over a 60-minute event-time window (D-053).

All of it happens in one transaction per event.

## Modules (`sentinelx_detection/`)
| Module | Role |
|---|---|
| `contract.py` | jsonschema validation against the generated contract (D-042); error messages never echo values |
| `models.py` | `Event`, `Signal`, severity bands |
| `context.py` | history windows; `InMemoryHistory` mirrors the PostgreSQL semantics |
| `rules.py` | the nine deterministic rules (D-048) |
| `features.py` | 16-feature vector (D-049) |
| `baseline.py`, `anomaly.py`, `train.py` | seeded synthetic baseline, Isolation Forest training/scoring, artifact save/load |
| `risk.py` | risk score, levels, alert threshold 40 (D-050) |
| `pipeline.py` | one event → signals, anomaly, risk |
| `correlation.py` | pure correlation plan (link/create/none), incident titles, alert reasons (D-052, D-053) |
| `repository.py` | psycopg queries (IPv4-preferring, time-bounded `connect()`, D-051) |
| `worker.py` | Kafka consume loop with manual commits (D-047) |

## Setup
Python 3.12 (D-024).

```powershell
# Windows PowerShell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m sentinelx_detection.train      # writes models/iforest-v1.joblib (+ .json); deterministic
```

```sh
# POSIX
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m sentinelx_detection.train
```

## Run
```sh
python -m sentinelx_detection.worker                    # long-running; Ctrl+C stops after the current event
python -m sentinelx_detection.worker --idle-exit 15     # process the backlog, then exit
python -m sentinelx_detection.worker --group replay-1   # a new consumer group re-reads the topic (idempotent, D-055)
```
Environment (repo-root `.env`): `APP_DATABASE_URL` (connects as `sentinelx_app`, D-035), `KAFKA_BROKERS`, optional `KAFKA_EVENTS_TOPIC` (default `security-events`) and `DETECTION_GROUP_ID` (default `sentinelx-detection`). The model artifact is never committed and must be trained locally; `joblib.load` unpickles, so never load a downloaded artifact (D-049).

## Checks
`python -m ruff check .`, `python -m mypy`, `python -m pytest` (all run by `python scripts/verify.py`).
- Unit tests: rules, risk, features, contract, model, scenarios A/B/C.
- `tests/integration/` needs the Compose stack and Node: it creates a throwaway database through the Drizzle migrations and a unique Kafka topic, and checks that worker results equal the pure pipeline's.
