# 19 — Agent Ownership

Architect: architecture, contracts, cross-cutting decisions.

Frontend Engineer: `apps/web/` UI, accessibility and frontend tests.

Backend Engineer: Next.js server/API boundary, auth, validation and orchestration.

Detection Engineer: `services/detection/` rules, features, anomaly model, risk and correlation.

AI Agent Engineer: `services/ai/` LangGraph, tools, retrieval, Ollama and verdict validation.

Database Engineer: schema, migrations, seeds and DB tests.

Security Engineer: security review, auth, prompt injection and agent permissions.

Test Engineer: cross-service and E2E tests.

Reviewer: adversarial phase gate.

Shared files such as Docker Compose, API contracts, root README, CI and phase docs require review when they affect another ownership boundary.
