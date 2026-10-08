-- Sessions are created, read and revoked (revoked_at) by the web app only (D-034, D-035).
-- No DELETE: revocation is an UPDATE. The AI roles get no access.
GRANT SELECT, INSERT, UPDATE ON analyst_sessions TO sentinelx_app;
