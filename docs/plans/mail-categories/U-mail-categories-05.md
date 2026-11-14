---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-05: Judging against the list

- Component: mail-triage
- Layer: backend
- Release: R1
- Contract: Rebuilt `Judgement` (category id from a closed set next to `urgent`), fixed urgency rules in the system prompt, descriptions in a separate data block, `resolve()` (unknown id to 'Other', urgency kept; invalid answer stays needs-attention), one mail per call, pinned-mail check (topmost `Authentication-Results` from `mx.google.com`, `dmarc=pass`, `header.from` on the allow-list), `filing` row per labelled mail, `MAX_CATEGORIES` removed.
- Files: agents/mail-triage/app/core/judgement.py, agents/mail-triage/app/core/pinned.py, agents/mail-triage/app/adapters/judge_anthropic.py, agents/mail-triage/app/usecases/triage.py, agents/mail-triage/tests/test_judgement_*.py
- Depends on: U-mail-categories-01, U-mail-categories-02, U-mail-categories-03
- Parallel: no
- Guardrails: guardrail-python, guardrail-pytest, guardrail-llm, guardrail-gmail
- Criteria:
  1. Given a list of 40 categories, When mail is judged, Then every category can be used and the mail carries exactly one label of the list or `Assistant/Other` (AC-5, AC-8) (type: happy)
  2. Given the hostile corpus of the stub model, When processed, Then the mail goes to 'Other' with no extra Gmail call and no database write other than the filing (AC-6, AC-7) (type: security)
  3. Given a description 'Other: everything', When an urgent mail arrives, Then it still raises the alert; an unknown id keeps `urgent` (AC-38) (type: security)
  4. Given the app's own sign-in mail or a Google security mail with DMARC pass on the allow-list, Then it stays in the inbox whatever the list says and the filing is not written (AC-39) (type: security)
  5. Given a forged `Authentication-Results` header lower in the mail, or a `header.from` that differs, Then the mail is not pinned (MC-19) (type: security)
  6. Given a filing, Then the list version used is recorded in `filing` without sender or subject (AC-39) (type: happy)
  7. Given descriptions, Then they are escaped and limited like mail text and one mail is judged per call (C-4) (type: security)
