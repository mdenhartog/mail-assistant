---
intent: INT-002
feature: web-settings
---

# U-web-settings-03: Clock, IdSource, CodeSource, fakes and the canary log check (R1)

- Layer: backend
- Contract: `Clock.now() -> datetime` (aware UTC; `SystemClock`), `IdSource` (`token(nbytes)`, `session_id()`, `login_request_id()`, `request_id()`), `CodeSource.six_digits() -> str` (`secrets`), in `app/clock.py`, `app/ids.py`, `app/codes.py`; test fakes `FakeClock` (settable), `FakeIds` (counting), `FakeCodes` (scripted) in `backend/tests/fakes.py`; the canary log check in `backend/tests/conftest.py`; the AST rule test.
- Files: `backend/app/clock.py`, `backend/app/ids.py`, `backend/app/codes.py`, `backend/tests/fakes.py`, `backend/tests/conftest.py`, `backend/tests/test_time_and_randomness_rule.py`
- Depends on: U-web-settings-02
- Parallel: no
- Guardrails: guardrail-python, guardrail-pytest
- Criteria:
  1. Given `SystemClock.now()`, When called, Then the result is timezone-aware UTC; `FakeClock` returns exactly what was set and moves only when told to (type: happy; level: unit).
  2. Given the production `IdSource`, When it makes 1000 tokens of 32 bytes, Then all are distinct, 43 URL-safe characters long and come from `secrets` (type: security; level: unit).
  3. Given the production `CodeSource`, When it makes 10000 codes, Then each is exactly six decimal digits including leading zeros, and a code below 100000 occurs (no integer truncation) (type: edge; level: unit).
  4. Given `FakeCodes(["123456", "654321"])`, When asked three times, Then the first two values, then a clear error (type: error; level: unit).
  5. Given every module of `backend/app`, When parsed with `ast`, Then `datetime.now`, `datetime.utcnow`, `time.time`, `date.today`, `uuid4`, `random.*` and `secrets.*` are called only in `clock.py`, `ids.py` and `codes.py`; a planted call in another module makes the test fail (type: security; level: unit).
  6. Given a test that logs a canary (`canary-user`, `424242`, `Pacific/Kiritimati`, `canary-smtp-secret`), When it ends, Then the shared check fails that test and names the canary and the logger (type: security; level: unit).
  7. Given the canary check and a test that did not log a canary, When it ends, Then it passes (type: happy; level: unit).
