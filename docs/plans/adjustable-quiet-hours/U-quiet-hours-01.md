---
intent: INT-002
feature: adjustable-quiet-hours
---

# U-quiet-hours-01: Schedule policy, validation and time parsing

- Layer: backend (shared package)
- Contract: `TimePolicy` (frozen: zone, quiet_start, quiet_end, overview_at, remind_at), `DEFAULT_POLICY`, `validate(policy) -> list[Problem]` (rule id, value given, example), `parse_time(text) -> time | None` (C-3); test helpers `make_policy`, `FakeClock`.
- Files: `packages/schedule-policy/pyproject.toml`, `schedule_policy/policy.py`, `schedule_policy/parse.py`, `schedule_policy/testing.py`, `packages/schedule-policy/tests/`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-pydantic
- Criteria:
  1. Given the defaults, When validated, Then there are no problems (AC-1) (type: happy).
  2. Given windows 23:00-07:00, 07:00-19:00, 07:00-08:00, When validated, Then valid; Given 07:00-19:01, 07:00-07:30, 23:00-23:00, Then each refused with its rule and an example (AC-10) (type: edge).
  3. Given overview 06:00 with window 23:00-07:00, or overview 18:00 with window 17:00-03:00, When validated, Then refused naming the overview, with a suggested move outside the window (AC-11) (type: error).
  4. Given the times `7`, `7:00`, `07:00`, `0700`, `19.30`, `7am`, `7:30pm`, `24:00`, When parsed, Then each gives the right clock time (AC-8) (type: happy).
  5. Given `abc`, `25:00`, `07:00:30`, a full-width `０７:００`, empty text, 65 characters, a control character, an emoji, When parsed, Then `None` (AC-9) (type: security).
  6. Given an unknown zone name or a path-like name, When validated, Then refused (type: security).
  7. Given any policy that passes validation, When the window length is computed on any day, Then it is 1 to 12 hours in clock minutes (property test) (type: edge).
  8. Given a reminder default inside the window, or an overview or reminder time exactly at the window start (refused) or at its end (valid), When validated, Then the start-inclusive, end-exclusive rule applies (type: edge).
  9. Given the property test, When run, Then it uses a fixed seed (`derandomize`) and the 59/60 and 720/721-minute boundaries are explicit rows (type: edge).
  10. Given mutation testing on `policy.py` and `parse.py`, When run, Then the score is at least 85 % (boundary mutants `<` vs `<=`, 59 vs 60, 720 vs 721 are killed) (type: security).
