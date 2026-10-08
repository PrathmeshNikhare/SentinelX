# 05 — Investigation Agent

## Graph
`START -> load_incident -> analyze_evidence -> choose_next_action -> execute_tool -> store_evidence -> analyze_evidence -> build_verdict -> validate_verdict -> END`

State includes investigation_run_id, incident_id, incident, evidence[], available_tools[], actions_taken[], retrieval_refs[], verdict, requires_review, errors[], step_count.

Default maximum investigation steps: 8. Tool calls and result sizes are bounded.

The agent chooses evidence-gathering actions. It does NOT calculate the authoritative numeric risk score.

Failure behavior:
- tool timeout: trace failure and continue if possible;
- invalid tool args: reject action;
- invalid LLM JSON: retry once, then mark review;
- unsupported evidence ID: reject verdict;
- dependency unavailable: preserve incident and investigation failure state.

Do not request or persist hidden chain-of-thought. Persist only auditable trace metadata.
