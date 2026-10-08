"""Feature vector (D-049), contract parsing (D-042) and the Isolation Forest model."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest

from sentinelx_detection.anomaly import AnomalyModel, baseline_matrix, load, save, train
from sentinelx_detection.baseline import BaselineConfig, baseline_events
from sentinelx_detection.config import CONTRACTS_DIR
from sentinelx_detection.context import Reputation
from sentinelx_detection.contract import ContractError, parse_message
from sentinelx_detection.features import FEATURE_NAMES, extract

from .conftest import THURSDAY_AFTERNOON, make_context, make_event, prior, scenario_events


def test_feature_vector_shape_and_values() -> None:
    event = make_event(status="failed", source_ip="203.0.113.45")
    ctx = make_context(
        prior_events=(prior(2), prior(5, ip="10.10.1.20"), prior(90, status="success")),
        known_ips=frozenset({"10.10.1.20"}),
        reputation=Reputation("malicious", 90),
    )
    features = dict(zip(FEATURE_NAMES, extract(event, ctx), strict=True))
    assert len(FEATURE_NAMES) == 16
    assert features["hour_sin"] == pytest.approx(np.sin(2 * np.pi * 14 / 24))
    assert features["is_weekend"] == 0.0 and features["is_failure"] == 1.0
    assert features["type_authentication"] == 1.0 and features["type_process"] == 0.0
    assert features["failed_logins_15m"] == 3.0  # two prior failures + this one
    assert features["user_events_1h"] == 3.0
    assert features["distinct_ips_24h"] == 3.0  # two prior IPs + the current one
    assert features["is_new_ip"] == 1.0
    assert features["ip_reputation"] == 0.9


def test_unknown_reputation_defaults_to_quarter() -> None:
    assert extract(make_event(), make_context())[FEATURE_NAMES.index("ip_reputation")] == 0.25


def test_contract_accepts_the_shared_example_and_rejects_bad_messages() -> None:
    example = (CONTRACTS_DIR / "examples" / "normalized-event.json").read_text(encoding="utf-8")
    event = parse_message(example.encode())
    assert (event.event_id, event.user_id, event.occurred_at.isoformat()) == (
        "evt_123",
        "user_1",
        "2026-01-01T10:00:00+00:00",
    )

    data = json.loads(example)
    for broken, path in [
        ({**data, "user_id": "SECRET_Upper"}, "user_id"),
        ({**data, "source_ip": "999.1.1.1"}, "source_ip"),
        ({**data, "extra": 1}, "(root)"),
        ({k: v for k, v in data.items() if k != "status"}, "(root)"),
        ({**data, "schema_version": "v2"}, "schema_version"),
    ]:
        with pytest.raises(ContractError) as error:
            parse_message(json.dumps(broken))
        assert path in str(error.value)
        assert "SECRET" not in str(error.value)  # values are never echoed into logs
    for raw in (None, b"", b"{not json", b"\xff\xfe"):
        with pytest.raises(ContractError):
            parse_message(raw)


def test_baseline_is_deterministic() -> None:
    first, second = baseline_events(), baseline_events()
    assert len(first) > 5000
    assert [(e.event_id, e.occurred_at, e.source_ip) for e in first] == [
        (e.event_id, e.occurred_at, e.source_ip) for e in second
    ]
    assert baseline_events(BaselineConfig(seed=7))[0].occurred_at != first[0].occurred_at or len(
        baseline_events(BaselineConfig(seed=7))
    ) != len(first)


def test_training_is_reproducible(model: AnomalyModel) -> None:
    again = train()
    assert again.version == model.version
    probe = extract(make_event(), make_context())
    assert again.score(probe) == model.score(probe)


def test_anomaly_scores_are_bounded_and_separate_attack_from_baseline(model: AnomalyModel) -> None:
    baseline_scores = model.score_many(baseline_matrix(BaselineConfig()))
    assert ((baseline_scores >= 0.0) & (baseline_scores <= 1.0)).all()
    assert model.score_many([extract(make_event(), make_context())])[0] == model.score(
        extract(make_event(), make_context())
    )
    attack = scenario_events("A", THURSDAY_AFTERNOON)[0]  # failed login from a malicious, first-seen IP
    attack_score = model.score(extract(attack, make_context(reputation=Reputation("malicious", 90))))
    assert attack_score > float(np.percentile(baseline_scores, 95))


def test_artifact_round_trip_and_guards(model: AnomalyModel, tmp_path: Path) -> None:
    path = tmp_path / "iforest-v1.joblib"
    save(model, path, BaselineConfig())
    loaded = load(path)
    probe = extract(make_event(occurred_at=THURSDAY_AFTERNOON + timedelta(hours=1)), make_context())
    assert loaded.version == model.version and loaded.score(probe) == model.score(probe)

    metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    path.with_suffix(".json").write_text(json.dumps({**metadata, "feature_names": ["x"]}), encoding="utf-8")
    with pytest.raises(ValueError, match="feature list"):
        load(path)
    with pytest.raises(FileNotFoundError, match="sentinelx_detection.train"):
        load(tmp_path / "missing.joblib")
