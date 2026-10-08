"""Isolation Forest training, persistence and scoring (D-049)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import IsolationForest

from .baseline import DEFAULT_BASELINE, BaselineConfig, baseline_events, reputation_from_fixture
from .context import InMemoryHistory
from .features import FEATURE_NAMES, extract
from .rules import evaluate_rules

FOREST_PARAMS: dict[str, Any] = {
    "n_estimators": 200,
    "max_samples": 256,
    "contamination": "auto",
    "random_state": 42,
}
SCORE_STEEPNESS = 12.0


@dataclass(frozen=True)
class AnomalyModel:
    forest: Any
    version: str

    def score(self, features: Sequence[float]) -> float:
        """0-1, higher is more anomalous; 0.5 sits on sklearn's outlier boundary (decision_function = 0)."""
        return float(self.score_many([features])[0])

    def score_many(
        self, rows: Sequence[Sequence[float]] | np.ndarray[Any, np.dtype[np.float64]]
    ) -> np.ndarray[Any, np.dtype[np.float64]]:
        """Vectorized `score` (one tree walk per batch instead of per row)."""
        decisions = self.forest.decision_function(np.asarray(rows, dtype=float))
        return np.asarray(1.0 / (1.0 + np.exp(SCORE_STEEPNESS * decisions)), dtype=float)


def model_version(matrix: np.ndarray[Any, np.dtype[np.float64]]) -> str:
    """Content-addressed: changes whenever the training data, feature list, parameters or sklearn version change."""
    digest = hashlib.sha256(np.ascontiguousarray(matrix).tobytes())
    digest.update(
        json.dumps(
            {"features": FEATURE_NAMES, "params": FOREST_PARAMS, "sklearn": sklearn.__version__},
            sort_keys=True,
        ).encode()
    )
    return f"iforest-v1-{digest.hexdigest()[:12]}"


def baseline_matrix(config: BaselineConfig) -> np.ndarray[Any, np.dtype[np.float64]]:
    """Replays the baseline through the same history, rules and feature code the worker uses."""
    history = InMemoryHistory(reputation_from_fixture())
    rows = []
    for event in baseline_events(config):
        ctx = history.context_for(event)
        rows.append(extract(event, ctx))
        history.record(event, evaluate_rules(event, ctx))
    return np.asarray(rows, dtype=float)


def train(config: BaselineConfig = DEFAULT_BASELINE) -> AnomalyModel:
    matrix = baseline_matrix(config)
    forest = IsolationForest(**FOREST_PARAMS).fit(matrix)
    return AnomalyModel(forest=forest, version=model_version(matrix))


def save(model: AnomalyModel, path: Path, config: BaselineConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model.forest, path)
    metadata = {
        "version": model.version,
        "feature_names": list(FEATURE_NAMES),
        "params": FOREST_PARAMS,
        "baseline": asdict(config),
        "sklearn": sklearn.__version__,
    }
    path.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def load(path: Path) -> AnomalyModel:
    """Loads a locally trained artifact. joblib unpickles: never point this at a downloaded file (D-049)."""
    meta_path = path.with_suffix(".json")
    if not path.is_file() or not meta_path.is_file():
        raise FileNotFoundError(f"model artifact missing at {path}; run: python -m sentinelx_detection.train")
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    if tuple(metadata["feature_names"]) != FEATURE_NAMES:
        raise ValueError("model feature list does not match the code; retrain with python -m sentinelx_detection.train")
    if metadata["sklearn"] != sklearn.__version__:
        raise ValueError(
            f"model trained with scikit-learn {metadata['sklearn']}, installed {sklearn.__version__}; retrain"
        )
    return AnomalyModel(forest=joblib.load(path), version=str(metadata["version"]))  # noqa: S301 - local artifact only
