# Verify Phase

Act as a strict phase gate for the current phase, following `docs/18_HANDOFF_PROTOCOL.md`. Check the phase exit criteria in `docs/07_PHASES.md` against actual files, git diff, tests (`python scripts/verify.py` once it exists), security and docs. Do not trust claims without verification. A handoff is not required yet; it is written afterwards by `/handoff`.

Report `APPROVED`, `REJECTED` or `BLOCKED`, listing each exit criterion with its evidence. On REJECTED/BLOCKED, record the reason in `progress/STATUS.md`. Do not write the handoff.
