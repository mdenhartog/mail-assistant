---
intent: INT-001
feature: mail-triage
---

# U-mail-triage-07: Token store and one-time consent

- Layer: backend (adapter and command-line tool)
- Contract: `TokenStore.save(refresh_token)`, `.load()`; `python -m app.consent` runs the OAuth consent for the owner (PKCE) and stores the result.
- Files: `app/adapters/token_store.py`, `app/consent.py`, `tests/adapters/test_token_store.py`
- Depends on: U-01, U-09
- Parallel: no (needs the table from U-09)
- Guardrails: guardrail-oauth2-oidc, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given a refresh token, When saved, Then the stored value is encrypted and decrypts to the original (happy; AC-25).
  2. Given the database content, When read directly, Then the plain token is not present and the key is not in the database (security; AC-25).
  3. Given a wrong or missing key, When loading, Then it fails closed with no partial value (error).
  4. Given the consent flow, When it runs, Then it uses PKCE and `state` and asks only for the three scopes in ADR-0011 (security).
  5. Given consent output, When logged, Then no token or authorisation code appears (security; AC-24).
