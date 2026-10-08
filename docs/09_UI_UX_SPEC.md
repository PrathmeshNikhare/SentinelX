# 09 — UI/UX Specification

Desktop-first internal console with compact sidebar and content area.

Pages: `/`, `/incidents`, `/incidents/[id]`, `/events`, optional `/settings`.

Incident page order: identity/status -> risk/severity -> summary -> timeline -> detection signals -> evidence -> MITRE -> investigation trace -> verdict -> recommendations.

Visual language: restrained, professional, information-dense, accessible. Monospace for IPs, IDs and timestamps.

Every data view must handle loading, empty, error, success and degraded states. Demo data must be clearly labeled.
