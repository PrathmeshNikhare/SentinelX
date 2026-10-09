# 09 — UI/UX Specification

Desktop-first internal console with compact sidebar and content area.

Pages: `/`, `/incidents`, `/incidents/[id]`, `/events`, optional `/settings`.

Incident page order: identity/status -> risk/severity -> summary -> timeline -> detection signals -> evidence -> MITRE -> investigation trace -> verdict -> recommendations.

Visual language: restrained, professional, information-dense, accessible. Monospace for IPs, IDs and timestamps.

Every data view must handle loading, empty, error, success and degraded states. Demo data must be clearly labeled.

Implementation (Phase 11, D-074): `apps/web/src/app/(console)/incidents/[id]/page.tsx` renders the order above, using the sections in `src/components/incident/sections.tsx` and the pure helpers in `src/lib/investigation-view.ts`. The investigation trace sits before evidence so the reader sees how the evidence was gathered. The verdict separates AI-assessed severity and uncalibrated confidence from the deterministic risk; a review banner explains every validation finding; recommendations are labelled as suggestions for analyst approval. The page polls while a run is queued or running. `e2e/walkthrough.spec.ts` walks scenario A through every section.
