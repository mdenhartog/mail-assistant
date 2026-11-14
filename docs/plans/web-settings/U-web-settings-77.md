---
intent: INT-002
feature: web-settings
---

# U-web-settings-77: The sign-in username ignores surrounding spaces and letter case (R1; backend; D-24)

- Layer: backend
- Contract: one pure function `normalize_username(raw)` in `app/auth/request_code_rules.py` (strip, NFKC, `casefold`, NFKC, strip; stable when applied twice). It is applied to the typed username before it becomes the `username_key` of a login request, real or decoy, and to the configured `Settings.username` when the owner key is derived (request-code and verify-code). The request model validates length (1 to 64) and characters on the normalised value, so a name that is empty after trimming gives the same 422 as an empty one. The decoy path runs the same normalisation and the same steps (AC-30). The audit actor digest `web:<digest>` and every other long-term digest of the configured username are still made from the configured name as written. The mail, the masked address and the answers do not change. The page cannot say that an e-mail address was typed (an unknown name gets a decoy, ADR-0038); the fixed hint is U-78.
- Files: `backend/app/auth/request_code_rules.py`, `backend/app/auth/request_code.py`, `backend/app/auth/verify_code.py`, `backend/app/routers/auth.py`, `backend/tests/auth/test_request_code_rules.py`, `backend/tests/auth/test_username_normalisation.py`, `docs/specs/web-settings.md`, `docs/user-guide/web-settings.md`, `docs/security/web-settings-threat-model.md`
- Depends on: U-web-settings-17, U-web-settings-18, U-web-settings-50
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest, guardrail-fastapi, guardrail-pydantic
- Criteria:
  1. Given the configured username `marco` (or `Marco`), When `Marco`, ` marco ` , `MARCO` and `marco` each ask for a code, Then each gets a code mail and creates the same owner key (AC-3, AC-6) (type: happy; level: integration).
  2. Given an unknown name, When it asks for a code, Then it gets a decoy with the same answer, cookie and Retry-After as before, and the same steps run as for the owner (AC-30) (type: security; level: integration).
  3. Given the owner's e-mail address typed as username, When it asks for a code, Then it is still unknown: a decoy and no mail (AC-30) (type: security; level: integration).
  4. Given the configured name `Marco` and a fixed key, When a session starts, Then the audit digest is the one it was before this unit (type: regression; level: integration).
  5. Given any text, When normalised, Then the result is stable, plain lower-case names do not change, `ß` gives `ss`, full-width letters give plain ones and `İ` gives `i` with a combining dot (type: edge; level: unit).
  6. Given `request_code_rules.py`, When the mutation gate runs, Then no mutant survives (type: security; level: unit).
  7. Given a name that is empty or only spaces after trimming, or has a control character, When it asks for a code, Then the same 422 as an empty name (type: error; level: integration).
