"""FastAPI service (D-057, D-058, D-064): auth before parsing, health, readiness, contracts, queuing runs."""

from __future__ import annotations

import psycopg
import pytest
from fastapi.testclient import TestClient

from sentinelx_ai.app import create_app
from sentinelx_ai.config import Settings
from sentinelx_ai.contracts import InvestigationAccepted
from sentinelx_ai.store import StartResult, Store

from .conftest import TOKEN, FakeLlm

AUTH = {"Authorization": f"Bearer {TOKEN}"}
REQUEST = {"incident_id": "inc_3f9a2b1c4d5e6f70", "requested_by": "an_bf897b6605224d78"}


class QueueStore(Store):
    def __init__(self, outcome: StartResult | Exception) -> None:
        super().__init__("postgresql://unused.invalid/none")
        self.outcome = outcome

    def start_run(self, incident_id: str) -> StartResult:
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class RecordingRunner:
    def __init__(self) -> None:
        self.runs: list[tuple[str, str]] = []

    def run(self, run_id: str, incident_id: str) -> None:
        self.runs.append((run_id, incident_id))


@pytest.fixture
def api(settings: Settings) -> TestClient:
    return TestClient(create_app(settings, FakeLlm()))


def test_health_is_public_and_reveals_nothing(api: TestClient) -> None:
    response = api.get("/health")
    assert response.status_code == 200 and response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer wrong-token"}, {"Authorization": TOKEN}, {"Authorization": f"Basic {TOKEN}"}],
)
@pytest.mark.parametrize(("method", "path"), [("GET", "/v1/ready"), ("POST", "/v1/investigations"), ("GET", "/nope")])
def test_everything_but_health_requires_the_token(
    api: TestClient, headers: dict[str, str], method: str, path: str
) -> None:
    response = api.request(method, path, headers=headers, json={"garbage": True})
    assert response.status_code == 401  # before routing and body validation: no contract details leak
    assert response.json() == {"error": {"code": "unauthorized", "message": "A valid service token is required."}}


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_api_docs_are_disabled(api: TestClient, path: str) -> None:
    assert api.get(path, headers=AUTH).status_code == 404


def test_ready_reports_model_availability(settings: Settings) -> None:
    up = TestClient(create_app(settings, FakeLlm(available=True))).get("/v1/ready", headers=AUTH)
    assert up.status_code == 200 and up.json() == {"status": "ready", "model": "test-model"}
    down = TestClient(create_app(settings, FakeLlm(available=False))).get("/v1/ready", headers=AUTH)
    assert down.status_code == 503 and down.json()["error"]["code"] == "unavailable"


def test_a_queued_run_returns_202_and_runs_in_the_background(settings: Settings) -> None:
    runner = RecordingRunner()
    store = QueueStore(StartResult("queued", "run_0a1b2c3d4e5f6a7b"))
    response = TestClient(create_app(settings, FakeLlm(), store, runner)).post(
        "/v1/investigations", headers=AUTH, json=REQUEST
    )
    assert response.status_code == 202
    assert InvestigationAccepted.model_validate(response.json()).investigation_run_id == "run_0a1b2c3d4e5f6a7b"
    assert runner.runs == [("run_0a1b2c3d4e5f6a7b", REQUEST["incident_id"])]  # TestClient runs background tasks


@pytest.mark.parametrize(
    ("outcome", "status", "code"),
    [
        (StartResult("not_found"), 404, "not_found"),
        (StartResult("in_progress"), 409, "investigation_in_progress"),
        (psycopg.OperationalError("connection refused"), 503, "unavailable"),
    ],
)
def test_unqueued_requests_start_nothing(
    settings: Settings, outcome: StartResult | Exception, status: int, code: str
) -> None:
    runner = RecordingRunner()
    api = TestClient(create_app(settings, FakeLlm(), QueueStore(outcome), runner))
    response = api.post("/v1/investigations", headers=AUTH, json=REQUEST)
    assert response.status_code == status and response.json()["error"]["code"] == code
    assert "connection refused" not in response.text
    assert runner.runs == []


def test_investigation_contract_is_enforced(api: TestClient) -> None:
    for bad in ({**REQUEST, "incident_id": "inc_1"}, {**REQUEST, "extra": 1}, {"incident_id": REQUEST["incident_id"]}):
        response = api.post("/v1/investigations", headers=AUTH, json=bad)
        assert response.status_code == 400
        body = response.json()["error"]
        assert body["code"] == "validation_failed"
        assert "inc_1" not in response.text  # issues carry paths and types, never the submitted values

    not_json = api.post("/v1/investigations", headers={**AUTH, "content-type": "application/json"}, content=b"{nope")
    assert not_json.status_code == 400


def test_oversized_bodies_are_rejected(api: TestClient) -> None:
    response = api.post("/v1/investigations", headers=AUTH, content=b"x" * (16 * 1024 + 1))
    assert response.status_code == 413


def test_unknown_routes_and_methods_use_the_error_shape(api: TestClient) -> None:
    assert api.get("/v1/unknown", headers=AUTH).json()["error"]["code"] == "not_found"
    assert api.get("/v1/investigations", headers=AUTH).json()["error"]["code"] == "method_not_allowed"
