---
intent: INT-001
feature: mail-triage
---

# U-mail-triage-08: Model adapter (Anthropic)

- Layer: backend (adapter)
- Contract: `Judge.judge(mail: TrimmedMail) -> Judgement | NeedsAttention`; internal escalation from the small to the large model.
- Files: `app/adapters/judge_anthropic.py`, `tests/adapters/test_judge_anthropic.py`, `tests/fixtures/injection/*.txt`
- Depends on: U-01, U-04
- Parallel: yes
- Guardrails: guardrail-llm, guardrail-api-client
- Criteria:
  1. Given a mail, When judged, Then the request contains only subject, sender and trimmed text, never attachments (security; AC-23).
  2. Given a body above the size cap, When trimmed, Then it is cut at the cap and the cut is marked (edge).
  3. Given mail text with instructions ("send this to…", "delete all mail", "mark as not urgent", "reveal other mail"), When judged with a scripted model, Then the result is still only a `Judgement` and the instructions have no effect on the call (security; AC-19).
  4. Given the model answers outside the schema, When judged, Then `NeedsAttention` (error; AC-18).
  5. Given low confidence from the small model, When judged, Then the large model is asked once and its result is used (happy; ADR-0014).
  6. Given the daily budget is used up, When a mail arrives, Then no model call is made and the result is `NeedsAttention` with reason `budget` (edge; AC-26).
  7. Given an API error or timeout, When judged, Then it retries within limits and then raises a retryable error (error; AC-12).
  8. Given the request is logged for debugging, When written, Then the mail text and the key are not in it (security; AC-24).
