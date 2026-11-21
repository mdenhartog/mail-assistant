---
intent: INT-008
feature: label-structure
---

# U-label-structure-07: One authenticated-sender verifier (R1)

- Component: mail-triage
- Layer: backend
- Contract: `authenticated_from_domain(headers, from_header) -> str | None` in `core/authentication.py` (ADR-0054): only the topmost `Authentication-Results` header from `mx.google.com` with `dmarc=pass` and `header.from` equal to the `From` domain counts. `core/pinned.py` (pinned mail, ADR-0045, ADR-0048) uses it; the weaker `core/auth_results.py` parser is removed.
- Files: `agents/mail-triage/app/core/authentication.py`, `agents/mail-triage/app/core/pinned.py`, `agents/mail-triage/app/core/auth_results.py` (removed), tests
- Depends on: U-label-structure-01
- Parallel: yes
- Guardrails: guardrail-python, guardrail-gmail, guardrail-pytest
- Criteria:
  1. Given a topmost Gmail header with `dmarc=pass` and the matching `header.from`, When verified, Then the From domain is returned. (type: happy)
  2. Given a topmost header not from `mx.google.com`, `dmarc=pass` only in a comment, `arc=` or `X-Original-Authentication-Results`, in an attached `message/rfc822`, two `dmarc=` results, `dmarc=fail`, no header, a different `header.from`, or folded and duplicated headers, When verified, Then the result is None. (type: security)
  3. Given a header the sender wrote into the message while Gmail added none, When verified, Then the result is None. (type: security)
  4. Given a missing, several or unparsable `From`, When verified, Then the result is None. (type: edge)
  5. Given the app's own sign-in code mail and Google security mail, When checked, Then pinned handling is unchanged and uses the same function (existing pinned tests stay green). (type: happy)
  6. Given the anonymised real Gmail headers, When verified, Then the expected results hold. (type: happy)
