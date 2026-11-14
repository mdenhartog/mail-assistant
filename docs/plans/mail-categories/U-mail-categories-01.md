---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-01: Test fakes and seed data

- Component: mail-triage
- Layer: backend
- Release: R1
- Contract: Test-only package `agents/mail-triage/tests/fakes/`: `FakeGmail` (label and message state machine: inbox, Archive, spam, trash, two Assistant labels, deleted mail and label, `Authentication-Results`; fault hooks: fail after the change and before the database write, 429, 5xx, a label created twice, a mail changed mid-apply), a contract test that keeps it aligned with the real Gmail wrapper, `FakeClock`, `BudgetLedger`, `FakeTelegram` (records text, checks canary strings), `StubModel` (hostile-output corpus), seed factories (1 000 items in 20 groups, 50 and 51 categories, 5 001 mails, NFKC look-alike names, bidi subjects, canaries).
- Files: agents/mail-triage/tests/fakes/*.py, agents/mail-triage/tests/test_fakes_*.py
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest
- Criteria:
  1. Given a fake mailbox, When labels are added, removed or created, Then the state follows Gmail's rules for inbox, Archive, spam, trash, two Assistant labels and deleted mail or label (type: happy)
  2. Given a fault hook 'fail after the change', When the caller changes a label, Then the fake keeps the change and raises, so a retry sees the mail already moved (type: error)
  3. Given two overlapping creates of the same label, When both run, Then the second gets 'already exists' (AC-25) (type: edge)
  4. Given the real Gmail wrapper and the fake, When the same operations run in a contract test, Then both give the same results for list, read, add, remove, create and rename (type: happy)
  5. Given the stub model, When asked for the hostile corpus, Then it returns an unknown id, two ids, markup, 'approve', an empty and a 1 001 character answer (type: security)
  6. Given the FakeTelegram and the canary strings, When a notice contains a canary, Then the fake fails the test (type: security)
  7. Given the seed factories, When called, Then they create 1 000 items in 20 groups, 50 and 51 categories, 5 001 in-scope mails, NFKC look-alikes and bidi subjects (type: edge)
