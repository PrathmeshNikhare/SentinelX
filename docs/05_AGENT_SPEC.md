# 05 — Investigation Agent

## Graph
`START -> load_incident -> analyze_evidence -> choose_next_action -> execute_tool -> store_evidence -> analyze_evidence -> build_verdict -> validate_verdict -> END`

`analyze_evidence` routes either to `choose_next_action` (more evidence needed and budget left) or to `build_verdict` (sufficient evidence, no useful action left, or step budget reached).

State includes investigation_run_id, incident_id, incident, evidence[], available_tools[], actions_taken[], retrieval_refs[], verdict, requires_review, errors[], step_count.

Default maximum investigation steps: 8. Tool calls and result sizes are bounded.

## Action selection (D-017)
The LLM proposes one action from `available_tools` as structured output. The proposal is validated against the tool input schema and the step budget. An invalid proposal, or an unavailable Ollama, falls back to a deterministic plan for the incident type. Every action is traced with `action_origin` (`llm` or `fallback`).

Knowledge and MITRE retrieval happen through `search_security_knowledge` and `get_mitre_technique` inside the loop. Every tool result, including retrieved knowledge, is stored as an evidence row (D-018).

The agent chooses evidence-gathering actions. It does NOT calculate the authoritative numeric risk score. Verdict `severity` is an AI assessment: a difference of two or more levels from the deterministic incident severity sets `requires_review=true`. `confidence` is model-reported and uncalibrated (D-016).

## Failure behavior
- tool timeout: trace failure and continue if possible;
- invalid tool args: reject action, use fallback;
- invalid LLM JSON: retry once, then mark review;
- unsupported evidence ID or unknown MITRE ID: reject verdict, keep raw output (D-019);
- dependency unavailable: preserve incident and investigation failure state.

Do not request or persist hidden chain-of-thought. Persist only auditable trace metadata.

## Implementation (Phase 08)
`services/ai/sentinelx_ai/graph.py` (graph, prompts, fallback plan, `Investigator`), `store.py` (writer-role persistence), `evidence.py` (code-written claims). Decisions: D-064 (flow, trace rows), D-065 (writer role, run lifecycle), D-066 (evidence and fallback plan), D-067 (no knowledge search before Phase 09), D-068 (verdict attempts and review).
