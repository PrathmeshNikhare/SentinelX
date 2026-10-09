# 06 — Tool Specification

All tools are read-only and typed. Database-backed tools use the SELECT-only role (D-022) through fixed parameterized queries.

## get_user_history
Input: user_id, start_time, end_time, limit. Bounded time window and result count.

## get_ip_reputation
Input: ip. Return attributes from the local `ip_reputation` table (D-020); unknown IPs return `unknown`. No external calls.

## get_related_logs
Input: optional user_id/source_ip, time range, optional event_types, limit. Bounded results.

## get_mitre_technique
Input: technique_id. Return the row from the local `mitre_techniques` table (D-020); unknown IDs return a typed not-found result.

## search_security_knowledge
Input: query, top_k (bounded). Retrieve from Qdrant through a retriever interface (fake in Phase 07, Qdrant in Phase 09; D-026). Results carry `knowledge_documents` source IDs.

Forbidden tool capabilities: raw SQL, filesystem access, shell execution, arbitrary HTTP, arbitrary Python, mutation actions.

Every tool requires input/output schemas, timeout, maximum result size, read-only declaration and tests.

Implementation (Phase 07): `services/ai/sentinelx_ai/tools.py`. `build_tools(ToolDatabase(AI_TOOLS_DATABASE_URL), retriever)` returns exactly these five LangChain `StructuredTool`s with `metadata.read_only = true` (D-060). The tools connect only as `sentinelx_ai_tools` in read-only, 2-second statement-timeout sessions (D-061). Bounds: window ≤ 7 days, limit ≤ 50, `top_k` ≤ 10, results ≤ 32 KiB (D-062). The retriever contract is in D-063. Without a retriever, `build_tools(db, None)` omits knowledge search (D-067).
