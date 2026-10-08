# 03 — End-to-End Workflow

## Detection
1. Submit event.
2. Validate and normalize.
3. Publish to Kafka.
4. Detection worker consumes.
5. Evaluate deterministic rules.
6. Extract ML features.
7. Run Isolation Forest.
8. Calculate deterministic risk.
9. Persist signals.
10. Correlate alerts.
11. Create/update incident.
12. Expose incident to UI.

## Investigation
1. Analyst opens incident.
2. Starts investigation.
3. LangGraph loads incident.
4. Evaluates evidence.
5. Chooses bounded tool action.
6. Tool executes.
7. Result becomes evidence.
8. Graph decides whether more evidence is needed.
9. Retrieve security knowledge/MITRE.
10. Ollama produces structured verdict.
11. Validate schema and evidence references.
12. Invalid/unsupported result becomes `requires_review=true`.
13. Persist trace and verdict.
14. UI renders evidence and recommendations.

## Demo chain
5 failed logins -> successful login -> new/high-risk IP -> PowerShell -> sensitive file access -> high anomaly -> risk ~90 -> incident -> evidence gathering -> MITRE retrieval -> evidence-backed Possible Account Compromise verdict.
