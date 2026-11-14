---
intent: INT-002
feature: web-settings
---

# U-web-settings-11: Pure rules for time: code life, attempts, cooldown, hourly cap, session expiry (R1)

- Layer: backend (pure module; mutation-gated)
- Contract: `app/auth/code_rules.py` (`code_expired(created_at, now, ttl)`, `attempts_exhausted(attempts, max)`, `register_wrong(attempts, max) -> (attempts, dead)`, `cooldown_remaining(last_requested_at, now, cooldown) -> int` over every request, `hourly_cap_reached(sent_times, now, cap)` over sent codes only) and `app/auth/expiry.py` (`idle_expired`, `absolute_expired`, `next_idle_expiry`). Standard library only, marker as in U-10.
- Files: `backend/app/auth/code_rules.py`, `backend/app/auth/expiry.py`, `backend/tests/auth/test_time_rules.py`, `backend/mutation/code_rules.exclusions`
- Depends on: U-web-settings-02
- Parallel: yes (with U-10)
- Guardrails: guardrail-python, guardrail-pytest
- Criteria:
  1. Given a code created at 14:00:00 with a 600 s life, When asked at 14:09:59 and 14:10:00, Then not expired, then expired (AC-3) (type: edge; level: unit).
  2. Given a code with 4 and 5 wrong attempts, When one more wrong code is registered, Then the fifth wrong attempt kills the code (attempt 5 dead, attempt 4 alive) and a sixth is refused without a comparison (AC-3, AC-5) (type: edge; level: unit).
  3. Given the last request at 14:00:00 (sent or not) and a 60 s cooldown, When asked at 14:00:59 and 14:01:00, Then 1 second remains, then 0 (AC-5, AC-31) (type: edge; level: unit).
  4. Given sent codes at 13:00:01 and later (failed sends are not in the list), When asked at 14:00:00 and 14:00:01, Then the first send still counts, then it falls out of the hour; with 4 sent codes in the hour the cap is not reached, with 5 it is (AC-5, AC-31) (type: edge; level: unit). Superseded by D-16 and U-53: every request counts from `created_at`, sent or not.
  5. Given a session last seen at 14:00:00, When asked at 14:29:59 and 14:30:00, Then valid, then idle-expired (AC-7) (type: edge; level: unit).
  6. Given a session created at 08:00:00 with activity every 20 minutes, When asked at 19:59:59 and 20:00:00, Then valid, then absolute-expired (AC-7) (type: edge; level: unit).
  7. Given naive datetimes, When passed in, Then an error (type: error; level: unit).
  8. Given every module of this unit, When imports are read, Then only the standard library (type: edge; level: unit).
  9. Given the baseline mutation run, When it finishes, Then the score is at least 85 % or every survivor is on the committed exclusion list (type: security; level: unit).
