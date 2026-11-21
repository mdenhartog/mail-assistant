---
intent: INT-008
feature: label-structure
---

# U-label-structure-08: Sender-rule filing (R1)

- Component: mail-triage
- Layer: backend
- Contract: in the filing flow (ADR-0054): pinned check, then the sender rule (`authenticated_from_domain` then the matcher from `category-policy`) files the mail under the topic and the extra label that list the sender without a category call; the filing record names the source (`sender_rule` with the entry, `model`, or `sender_rule_not_applied`); an unticked category gets one urgency-only call (the call itself is U-label-structure-09; here it is a port with a fake); the matcher is built once per list version; it writes the filing row with `extra_id`, `source` (`sender_rule`, `sender_rule_not_applied` or `model`) and `source_ref` (the matched entry) on the columns that unit 32 made the only ones (the switch from `filing.category_id` and the migration `0025` are unit 32, split out to keep this unit small).
- Files: `agents/mail-triage/app/usecases/triage.py`, `agents/mail-triage/app/core/sender_rules.py`, `agents/mail-triage/app/db/pg_store.py` (filing), tests
- Depends on: U-label-structure-01, U-label-structure-02, U-label-structure-03, U-label-structure-05, U-label-structure-07, U-label-structure-32
- Parallel: no
- Guardrails: guardrail-python, guardrail-gmail, guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given a listed, authenticated sender, When its mail is processed, Then it is filed in that category and the fake model gets no category call. (type: happy)
  2. Given a category with no senders, When a mail arrives, Then the model judges it as before. (type: happy)
  3. Given a mail whose sender matches a topic category and an extra-label category, When processed, Then it is filed under both without a category call. (type: edge)
  4. Given a listed sender that is not authenticated, When processed, Then the model judges it and the filing record says "sender rule not applied: sender not authenticated". (type: security)
  5. Given the app's own sign-in code mail or Google security mail from a listed sender, When processed, Then pinned handling applies and no rule files it. (type: security)
  6. Given a sender-rule filing, an Undo and a Move back, When they run, Then they work as for a model-filed mail and the AC-46 report counts it. (type: edge)
  7. Given any decision, When it is made, Then only the authenticated From domain is used, never the display name, `Reply-To`, subject or body. (type: security)
