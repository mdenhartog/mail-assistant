---
intent: INT-002
feature: web-settings
---

# U-web-settings-24: In-process rate and body limits (R1; release gate)

- Layer: backend (pure module; mutation-gated)
- Contract: ADR-0034. Pure `app/limits.py` (`window_key(now) = floor(now / 60)`, fixed-window counter per client and bucket, bounded memory) and `app/clientaddr.py` (`client_key(peer, xff, trusted_cidrs, hops)`: the address the last trusted proxy appended; any other peer by its own address); the real `LimitGuard` replaces the no-op of U-05 for the buckets `signin` and `api`; body limit 8192 bytes (413, also chunked bodies without a length); a refused request records one `rate_limited` event per client and window. Limit values come from the settings of U-04 only.
- Files: `backend/app/limits.py`, `backend/app/clientaddr.py`, `backend/app/limit_guard.py`, `backend/app/middleware.py`, `backend/tests/test_limits.py`
- Depends on: U-web-settings-05, U-web-settings-13, U-web-settings-17, U-web-settings-18
- Parallel: yes (with U-19 to U-23)
- Guardrails: guardrail-fastapi, guardrail-python
- Criteria:
  1. Given 30 requests to `/auth/request-code` in one window, When the 31st arrives, Then 429 with an integer `Retry-After`; at 59.9 s still the same window, at 60.0 s a new window passes (AC-16, W-7) (type: edge; level: api).
  2. Given the `api` bucket on `/api/settings`, When one client exceeds it, Then 429 and the `signin` bucket is unaffected (AC-16) (type: edge; level: api).
  3. Given the limit is exceeded on the sign-in routes, When the database is read, Then no `login_request` row was written for the refused requests (AC-16, W-7) (type: security; level: db).
  4. Given `X-Forwarded-For: spoof, real` where the last trusted proxy appended `real`, When keyed, Then the key is `real`; a spoofed leftmost value never opens a fresh bucket; a peer outside the trusted CIDRs is keyed by its own address (W-7, W-17) (type: security; level: unit).
  5. Given a body of 8192 and 8193 bytes, and a chunked body over the limit, When sent to a write route, Then accepted, 413, 413, and the body is not parsed (AC-16) (type: edge; level: api).
  6. Given a flood from one client, When refused, Then exactly one `rate_limited` event exists for that client and window (AC-20, W-13) (type: security; level: db).
  7. Given limits lowered through settings (tests use 3), When the guard runs, Then they take effect; there is no second definition of a limit outside the settings (type: happy; level: unit).
  8. Given many distinct clients over many windows, When counters are held, Then windows older than two are dropped and the size stays bounded (W-7) (type: edge; level: unit).
  9. Given `window_key` at 59.9 s, 60.0 s and 60.1 s, When called, Then 0, 1 and 1 (type: edge; level: unit).
  10. Given the baseline mutation run of `limits.py` and `clientaddr.py`, When it finishes, Then the score is at least 85 % or every survivor is on the committed exclusion list (type: security; level: unit).
