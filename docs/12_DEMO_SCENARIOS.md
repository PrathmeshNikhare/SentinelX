# 12 — Demo Scenarios

## A — Possible Account Compromise
5 failed logins -> successful login from new IP -> high-risk reputation -> PowerShell -> sensitive file access.
Expected: brute-force, unusual-login and PowerShell signals; elevated anomaly; HIGH/CRITICAL risk; incident; investigation; evidence-backed compromise verdict.

## B — Benign Admin Activity
Expected maintenance from known IP with normal access. Expected low/medium risk and no invented compromise.

## C — Anomalous but Unclear
Unusual time/IP without known malicious command. Expected anomaly and cautious verification-oriented verdict.

Every scenario must be generated deterministically from fixtures/scripts.
