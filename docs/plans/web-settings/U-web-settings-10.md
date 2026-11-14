---
intent: INT-002
feature: web-settings
---

# U-web-settings-10: Pure rules for the code: hash, mask, username digest, return path (R1)

- Layer: backend (pure module; mutation-gated)
- Contract: `app/auth/code_hash.py` (`hash_code(key, request_id, code) -> bytes` HMAC-SHA-256 over request id and code, `verify_code(...)` with `hmac.compare_digest`), `app/auth/mask.py` (`mask_address("marco@example.com") -> "m***@example.com"`), `app/auth/digest.py` (`username_digest(key, username) -> 32 lower-case hex`, also the `updated_by` value `web:<32 hex>`), `app/auth/return_to.py` (`safe_return_to(value) -> "/settings"`). All import only the standard library, carry the marker `# pure module (mutation-gated)` and are checked by `tests/test_pure_modules.py`. This unit also adds the local mutation runner `backend/mutation/run.py <module>` (annotations excluded).
- Files: `backend/app/auth/code_hash.py`, `backend/app/auth/mask.py`, `backend/app/auth/digest.py`, `backend/app/auth/return_to.py`, `backend/tests/auth/test_code_rules.py`, `backend/tests/test_pure_modules.py`, `backend/mutation/run.py`
- Depends on: U-web-settings-02
- Parallel: yes (with U-03 to U-05)
- Guardrails: guardrail-python, guardrail-pytest, guardrail-oauth2-oidc
- Criteria:
  1. Given a key, request id and code, When hashed twice, Then the result is identical, 32 bytes, differs for another key, another request id or another code (W-1) (type: happy; level: unit).
  2. Given the right code and `123456` vs `123457`, When verified, Then true and false; Given a code with spaces or letters, Then false without an exception (AC-3) (type: edge; level: unit).
  3. Given the verifier, When timed with a matching and a non-matching code of the same length, Then it calls `hmac.compare_digest` (checked by patching it) and never `==` on the digests (W-1) (type: security; level: unit).
  4. Given `marco@example.com`, `a@example.com` and `very.long.name@sub.example.org`, When masked, Then `m***@example.com`, `a***@example.com`, `v***@sub.example.org`; the full local part never appears (W-15) (type: security; level: unit).
  5. Given `username_digest` with two keys and two usernames, When called, Then results differ, are 32 lower-case hex characters, stable for equal input, and the plain username is not a substring (W-10, W-15) (type: security; level: unit).
  6. Given `return_to` values `https://evil.example`, `//evil.example`, `/\evil`, `javascript:alert(1)`, `/settings/../x`, `/other`, an empty value and `None`, When processed, Then `/settings` each; `/settings` stays `/settings` (AC-6, W-2) (type: security; level: unit).
  7. Given every module of this unit, When their imports are read, Then none imports FastAPI, SQLAlchemy, httpx or the network; the marker test lists them (type: edge; level: unit).
  8. Given the baseline mutation run of the four modules, When it finishes, Then the score is at least 85 % or every survivor is on the committed `backend/mutation/<module>.exclusions` list with a reason (type: security; level: unit).
