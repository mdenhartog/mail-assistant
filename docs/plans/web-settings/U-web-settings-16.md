---
intent: INT-002
feature: web-settings
---

# U-web-settings-16: Login request store (R1)

- Layer: backend (database)
- Contract: `LoginRequests.create(username_key, code, now, cap) -> LoginRequest` marks any live request of that username dead and inserts a new row with the code hash (U-10) and expiry; `check(request_id, code, now) -> Verdict` in one transaction (`SELECT ... FOR UPDATE`): `Ok` (row marked dead, single use), `Wrong(attempts_left)`, `Dead`; `mark_sent(request_id, now)` (called only after a successful send), `last_requested_at(username_key)` (every request), `sent_in_last_hour(username_key, now)` (only rows with `sent_at`); open rows capped; rows older than one hour are removed on insert.
- Files: `backend/app/auth/login_requests.py`, `backend/tests/auth/test_login_requests.py`
- Depends on: U-web-settings-07, U-web-settings-09, U-web-settings-10, U-web-settings-11
- Parallel: yes (with U-12 to U-15)
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given a created request and the right code at 9:59 after creation, When checked, Then `Ok` and the row is dead; the same code again is `Dead` (AC-3) (type: happy; level: db).
  2. Given the right code at 10:00 after creation (`FakeClock`), When checked, Then `Dead` (expired) (AC-3) (type: edge; level: db).
  3. Given five wrong codes, When the fifth is checked, Then it returns `Dead`, and the right code after that is `Dead`; after four wrong codes the right code is still `Ok`; `attempts_left` counts 4, 3, 2, 1 (AC-3, AC-5) (type: edge; level: db).
  4. Given an old code and a newer code for the same username, When the old one is checked, Then `Dead` (replaced) (AC-3) (type: security; level: db).
  5. Given a request id of another browser, an unknown id and `None`, When checked, Then `Dead` for each, with no attempt counted on any other row (AC-3, W-1) (type: security; level: db).
  6. Given two checks of the right code at the same time with a barrier, When both run, Then exactly one is `Ok` (single use) (AC-3) (type: security; level: db).
  7. Given five codes created and marked sent within one hour, When `sent_in_last_hour` is read, Then 5 and the cap logic of U-11 refuses the sixth; a send 60 min 1 s old is no longer counted, one 59 min 59 s old is (AC-31) (type: edge; level: db).
  8. Given five requests whose send failed (never marked sent), When `sent_in_last_hour` and `last_requested_at` are read, Then 0 sent and the last request time is the newest creation time, so the cooldown applies and the cap does not (AC-29, AC-31) (type: edge; level: db).
  9. Given the cap of open requests, When one more is created, Then it is refused and no row is written (AC-16, W-7) (type: security; level: db).
  10. Given the table read as the owner, When inspected, Then no clear code is stored, only the hash (W-15) (type: security; level: db).
