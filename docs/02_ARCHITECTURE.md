# 02 — Architecture

As built (Phases 00–13). The reasons behind each component, with the alternatives rejected, are in `docs/23_INTERVIEW_GUIDE.md`; every decision is in `progress/DECISIONS.md`.

## System
```mermaid
flowchart LR
  analyst([Analyst browser])
  producer([Event producer<br/>demo:send, tools])

  subgraph web["Next.js console — 127.0.0.1:3000"]
    ui[Server-rendered pages<br/>incident UI, polling]
    api[JSON API<br/>/api/events · /api/incidents · /api/investigations]
  end

  subgraph det["Detection worker (Python)"]
    rules[Deterministic rules]
    iforest[Isolation Forest<br/>anomaly signal]
    risk[Risk engine 0–100]
    corr[Correlation<br/>per user, 60 min]
  end

  subgraph ai["AI service — FastAPI, internal only"]
    lg[LangGraph investigation<br/>≤ 8 tool steps]
    tools[5 typed read-only tools]
    ground[Verdict validation<br/>schema · evidence IDs · MITRE IDs · severity]
  end

  kafka[(Kafka<br/>security-events)]
  pg[(PostgreSQL<br/>events · signals · alerts · incidents<br/>runs · trace · evidence)]
  qdrant[(Qdrant<br/>security_knowledge)]
  ollama[[Ollama on the host<br/>llama3.2:3b]]

  analyst -->|session cookie| ui
  analyst --> api
  producer -->|Bearer ingest token| api
  api -->|validate, normalize, publish| kafka
  kafka --> rules --> iforest --> risk --> corr
  corr -->|sentinelx_app| pg
  ui -->|sentinelx_app, read| pg
  api -->|Bearer AI token: start run| lg
  lg -->|sentinelx_ai_writer<br/>runs, append-only trace and evidence| pg
  lg --> tools
  tools -->|sentinelx_ai_tools<br/>SELECT-only| pg
  tools -->|API key| qdrant
  lg -->|action proposals, verdict| ollama
  lg --> ground
```

Trust boundaries:
- Only the console is published, on 127.0.0.1. The AI service accepts only the Next.js server's token, and in Compose it is not published at all.
- Each service connects to PostgreSQL as its own least-privilege role. The agent's tools can only read.
- The LLM sees code-written evidence claims and produces a verdict, which code validates before anyone sees it. The model never sets the risk score.

## Investigation sequence
```mermaid
sequenceDiagram
  autonumber
  actor A as Analyst
  participant W as Next.js
  participant S as AI service
  participant G as LangGraph
  participant T as Tools (read-only)
  participant L as Ollama
  participant P as PostgreSQL
  A->>W: Investigate (server action)
  W->>S: POST /v1/investigations (token)
  S->>P: queue run (one active run per incident)
  S-->>W: 202 {investigation_run_id}
  W-->>A: page polls every 4 s
  S->>G: background task
  G->>P: load incident → event and alert evidence
  loop up to 8 tool steps
    G->>L: propose next action (JSON schema)
    alt valid, new, available
      G->>T: run tool
    else invalid or Ollama down
      G->>T: next step of the deterministic fallback plan
    end
    T-->>G: bounded result
    G->>P: append evidence and trace
  end
  G->>L: verdict (fenced evidence, supported MITRE IDs)
  G->>G: validate schema, evidence IDs, MITRE IDs, severity gap (retry once)
  G->>P: completed / requires_review / failed, every attempt kept
  A->>W: page shows trace, evidence, MITRE, verdict
```

## Deployment topologies
| | Development | Clean-machine demo |
|---|---|---|
| Command | `docker compose up -d` | `docker compose --profile app up -d --build` |
| In containers | PostgreSQL, Kafka, Qdrant | the same, plus `setup` and `knowledge` (one-shot), `web`, `detection`, `ai` |
| On the host | Next.js, the detection worker, the AI service, Ollama | Ollama only |
| Gate | `python scripts/verify.py` (24 checks) | `apps/web/demo-check` (docs/22) |

## Boundaries
- **Web** owns the UI, the session boundary and the user-facing APIs.
- **Detection** owns rules, features, the anomaly model, risk and correlation.
- **AI** owns LangGraph, the tools, retrieval, the LLM adapter, verdict validation and trace creation.
- **PostgreSQL** owns persistence. Drizzle migrations are the only DDL (D-010).

Cross-service payloads are versioned JSON Schemas in `contracts/v1/` (D-011, D-042, D-059).

Do not add a service without a concrete boundary and a documented reason.
