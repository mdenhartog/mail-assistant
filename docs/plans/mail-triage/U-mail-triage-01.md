---
intent: INT-001
feature: mail-triage
---

# U-mail-triage-01: Component skeleton and configuration

- Layer: backend (scaffold from `/sdlc:component agent mail-triage`, then adapted)
- Contract: `Settings` (pydantic-settings) loaded from environment; fails at startup when a required secret or id is missing; component registered in `.sdlc/components.json`.
- Files: `agents/mail-triage/pyproject.toml`, `app/settings.py`, `app/main.py`, `tests/test_settings.py`, `.sdlc/components.json`
- Depends on: —
- Parallel: no
- Guardrails: guardrail-pydantic, guardrail-docker, guardrail-llm
- Criteria:
  1. Given all required values, When settings load, Then they are typed and defaults match spec C1; quiet hours, overview time and time zone are not settings (they are constants, spec C7) (happy).
  2. Given a missing `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN` or allowed user id, When the app starts, Then it refuses to start with a message that names the missing key but not any value (error, security).
  3. Given settings are printed or logged, When secrets are present, Then they appear masked (security).
  4. Given model ids, When configured, Then no model id literal exists in code (edge).
