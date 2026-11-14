---
intent: INT-002
feature: web-settings
---

# U-web-settings-39: Prod-like TLS database (R1)

- Layer: infra
- Contract: PostgreSQL in the prod-like profile serves TLS with a certificate from the internal CA for the host name `db`; the web role's `DATABASE_URL` uses the asyncpg `ssl` setting with `verify-full` (not libpq `sslmode`) and the CA file; the migrate service in the profile runs with the web role password (U-08).
- Files: `compose.yaml`, `deploy/prod-like/db-tls.sh`, `backend/tests/e2e/test_db_tls.py`
- Depends on: U-web-settings-08, U-web-settings-09, U-web-settings-37
- Parallel: yes (with U-38)
- Guardrails: guardrail-compose, guardrail-docker, guardrail-tls-certificates, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given the stack, When the api connects as the web role, Then the connection is TLS and `/readyz` is 200 (W-8, W-9) (type: happy; level: image).
  2. Given a connection by an alias that is not in the certificate, When the engine of U-09 connects, Then it is rejected with a host name error (W-9) (type: security; level: image).
  3. Given a CA file that did not sign the server certificate, When the engine connects, Then it is rejected (W-9) (type: security; level: image).
  4. Given a plain, non-TLS connection attempt as the web role, When made to the server, Then the server refuses it (W-9) (type: security; level: image).
  5. Given the migrate service in the profile, When it runs, Then both roles exist and no runtime container uses the owner credentials (AC-17) (type: security; level: image).
  6. Given `docker compose config`, When searched, Then no literal password or URL with a password (type: security; level: ci).
