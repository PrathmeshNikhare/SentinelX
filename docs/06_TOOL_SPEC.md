# 06 — Tool Specification

All tools are read-only and typed.

## get_user_history
Input: user_id, start_time, end_time, limit. Bounded time window and result count.

## get_ip_reputation
Input: ip. Return local/mock reputation attributes. No uncontrolled external calls.

## get_related_logs
Input: optional user_id/source_ip, time range, optional event_types, limit. Bounded results.

## get_mitre_technique
Input: technique_id. Return approved local MITRE data.

## search_security_knowledge
Input: query, top_k. Retrieve from Qdrant.

Forbidden tool capabilities: raw SQL, filesystem access, shell execution, arbitrary HTTP, arbitrary Python, mutation actions.

Every tool requires input/output schemas, timeout, maximum result size, read-only declaration and tests.
