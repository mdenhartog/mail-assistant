---
intent: INT-001
feature: mail-triage
---

# U-mail-triage-17: Log and error-report redaction

- Layer: backend (cross-cutting)
- Contract: logging filter and Sentry `before_send` that remove mail text, tokens, the API key and URLs with the bot token.
- Files: `app/obs/redaction.py`, `tests/obs/test_redaction.py`
- Depends on: U-01
- Parallel: yes
- Guardrails: guardrail-python
- Criteria:
  1. Given a log record with a mail body, When emitted, Then the body is replaced (security; AC-14, AC-24).
  2. Given a URL `https://api.telegram.org/bot<token>/…`, When logged, Then the token part is masked (security; AC-24).
  3. Given an exception whose message contains the API key, When sent to Sentry, Then the key is scrubbed (security; AC-24).
  4. Given a Sentry event with local variables, When sent, Then variable values for secrets and bodies are removed (security).
  5. Given normal log lines, When emitted, Then ids and counts stay readable (edge).
