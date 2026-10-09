"""Evidence rows for investigations (D-018, D-066): deterministic one-line claims plus the bounded source data.

Claims are written by code, never by the model, so every evidence row says exactly what its data shows. Log fields are
attacker-controllable; they are clipped here and the prompts label them as untrusted data (docs/15).
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Final

from .store import IncidentContext, SourceType

MAX_FIELD_CHARS: Final = 120

EvidenceItem = tuple[SourceType, str, str, Any]  # (source_type, source_id, claim, data), as Store.add_evidence takes


def clip(value: object, limit: int = MAX_FIELD_CHARS) -> str:
    text = " ".join(str(value).split())  # collapses newlines so a log field cannot fake extra prompt lines
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _stamp(value: Any) -> str:
    return value.isoformat().replace("+00:00", "Z") if hasattr(value, "isoformat") else str(value)


def event_claim(event: dict[str, Any]) -> str:
    claim = (
        f"{_stamp(event['occurred_at'])} {clip(event['user_id'])} {event['event_type']}/{clip(event['action'])} "
        f"{event['status']} from {event['source_ip']} on {clip(event['resource'])}"
    )
    signals = event.get("signals") or []
    return claim + (f"; detection rules: {', '.join(signals)}" if signals else "")


def alert_claim(alert: dict[str, Any]) -> str:
    reasons = alert.get("reasons") or {}
    signals = ", ".join(f"{s['rule']} ({s['score']})" for s in reasons.get("signals", []))
    return (
        f"alert on event {alert['event_id']}: deterministic risk {alert['risk_score']} ({alert['severity']}), "
        f"anomaly {alert['anomaly_score']:.2f}" + (f", signals {signals}" if signals else "")
    )


def incident_evidence(ctx: IncidentContext) -> list[EvidenceItem]:
    events: list[EvidenceItem] = [("event", e["event_id"], event_claim(e), e) for e in ctx.events]
    alerts: list[EvidenceItem] = [("alert", a["alert_id"], alert_claim(a), a) for a in ctx.alerts]
    return events + alerts


def _events_summary(events: list[dict[str, Any]], truncated: bool) -> str:
    if not events:
        return "no events"
    failed = sum(1 for e in events if e["status"] == "failed")
    ips = Counter(e["source_ip"] for e in events)
    types = Counter(e["event_type"] for e in events)
    summary = (
        f"{len(events)}{'+' if truncated else ''} events ({failed} failed), "
        f"types {', '.join(f'{t} {n}' for t, n in types.most_common())}, "
        f"source IPs {', '.join(f'{ip} {n}' for ip, n in ips.most_common(3))}"
    )
    return summary + (f" and {len(ips) - 3} more" if len(ips) > 3 else "")


def tool_evidence(tool: str, arguments: dict[str, Any], result: dict[str, Any]) -> list[EvidenceItem]:
    """Evidence rows for one successful tool call; knowledge searches give one row per hit (D-018)."""
    if tool in ("get_user_history", "get_related_logs"):
        scope = ", ".join(f"{k} {arguments[k]}" for k in ("user_id", "source_ip") if arguments.get(k))
        if arguments.get("event_types"):
            scope += f", types {'/'.join(arguments['event_types'])}"
        window = f"{arguments['start_time']} to {arguments['end_time']}"
        claim = f"{tool} for {scope}, {window}: {_events_summary(result['events'], result['truncated'])}"
        if tool == "get_user_history":
            return [("user_history", arguments["user_id"], claim, result)]
        return [("related_logs", scope, claim, result)]
    if tool == "get_ip_reputation":
        if result["known"]:
            tags = ", ".join(result["tags"]) or "no tags"
            claim = f"IP {result['ip']} local reputation {result['reputation']} (score {result['score']}; {tags})"
        else:
            claim = f"IP {result['ip']} is not in the local reputation list (unknown)"
        return [("ip_reputation", result["ip"], claim, result)]
    if tool == "get_mitre_technique":
        if result["found"]:
            claim = (
                f"MITRE ATT&CK {result['technique_id']} {result['name']} ({', '.join(result['tactics'])}): "
                f"{clip(result['description'], 300)}"
            )
        else:
            claim = f"{result['technique_id']} is not in the curated MITRE ATT&CK set"
        return [("mitre", result["technique_id"], claim, result)]
    if tool == "search_security_knowledge":
        return [
            (
                "knowledge",
                hit["document_id"],
                f"{clip(hit['title'])} ({hit['source']}): {clip(hit['snippet'], 300)}",
                hit,
            )
            for hit in result["hits"]
        ]
    raise ValueError(f"no evidence mapping for tool {tool!r}")
