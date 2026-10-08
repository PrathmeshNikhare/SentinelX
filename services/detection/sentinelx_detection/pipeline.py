"""One event through rules, features, anomaly and risk (D-048 – D-050). Pure given the context and model."""

from __future__ import annotations

from dataclasses import dataclass

from .anomaly import AnomalyModel
from .context import DetectionContext
from .features import extract, reputation_score
from .models import Event, Severity, Signal
from .risk import context_score, risk_level, risk_score, should_alert
from .rules import evaluate_rules


@dataclass(frozen=True)
class DetectionResult:
    signals: tuple[Signal, ...]
    features: tuple[float, ...]
    anomaly_score: float
    risk_score: int
    risk_level: Severity
    model_version: str
    should_alert: bool  # persisted as an alert (D-052)
    reputation_score: int  # risk component P
    context_score: int  # risk component C


def detect(event: Event, ctx: DetectionContext, model: AnomalyModel) -> DetectionResult:
    signals = evaluate_rules(event, ctx)
    features = extract(event, ctx)
    anomaly = model.score(features)
    recent_rules = {s.rule_name for s in ctx.prior_signals} | {s.rule_name for s in signals}
    reputation = reputation_score(ctx)
    context = context_score(recent_rules)
    score = risk_score(
        rule_score=max((s.rule_score for s in signals), default=0),
        anomaly_score=anomaly,
        reputation_score=reputation,
        context=context,
    )
    return DetectionResult(
        signals=signals,
        features=features,
        anomaly_score=anomaly,
        risk_score=score,
        risk_level=risk_level(score),
        model_version=model.version,
        should_alert=should_alert(score),
        reputation_score=reputation,
        context_score=context,
    )
