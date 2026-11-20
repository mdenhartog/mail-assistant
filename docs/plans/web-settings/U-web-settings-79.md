---
intent: INT-002
feature: web-settings
---

# U-web-settings-79: The log check counts a code only as a whole number (R1; CI fix; U-web-settings-42)

- Layer: ci, backend tests
- Contract: `scripts/prodlike-checks.sh logs` reports a number (a sign-in code, or a canary code written by the canary test) only when it stands alone in a log line, so it no longer finds a code by chance inside a longer number such as the response time `0.007834233`; a text value (the canary username and zone, the SMTP password, the session cookie) is still found wherever it sits. The matching is one function, `log_files_matching`, that a test can call on small log files.
- Files: `scripts/prodlike-checks.sh`, `backend/tests/test_log_check_matching.py`
- Depends on: U-web-settings-42
- Parallel: yes
- Guardrails: guardrail-pytest, guardrail-python
- Criteria:
  1. Given a canary or sign-in code of six digits and a log line with a response time that contains those digits inside a longer number, When the log check matches, Then it is not a hit (type: security; level: unit).
  2. Given the same code standing alone in a log line (alone, in a query value, in quotes, after a colon), When the log check matches, Then it is a hit (type: security; level: unit).
  3. Given a text canary inside a longer word, When the log check matches, Then it is still a hit (type: security; level: unit).
