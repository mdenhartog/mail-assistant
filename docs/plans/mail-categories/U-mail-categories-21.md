---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-21: Run the list sync in the agent

- Component: mail-triage
- Layer: backend
- Release: R1
- Contract: the agent runs `ListSync` (U-06) at start and on a cadence (default every 60 seconds, like the settings poll), with the mailbox id and the cadence from configuration; a failed sync is logged without content and retried, and never stops mail triage; the sync runs before judging uses the list so that the first start seeds version 1 (AC-3) and a rename reaches Gmail within one cadence (AC-40).
- Files: agents/mail-triage/app/runner.py, agents/mail-triage/app/wiring.py, agents/mail-triage/app/settings.py, agents/mail-triage/compose.yaml, agents/mail-triage/tests/test_runner_list_sync.py
- Depends on: U-mail-categories-05, U-mail-categories-06
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest, guardrail-gmail
- Criteria:
  1. Given a first start with labels in Gmail and no list, When the agent starts, Then version 1 is seeded before any mail is judged (AC-3) (type: happy)
  2. Given a name-only change saved in the web app, When one cadence passes, Then the Gmail label is renamed by id (AC-40) (type: happy)
  3. Given a Gmail error in the sync, When it runs, Then mail triage continues, the error is logged without mail content and the next cadence retries (type: error)
  4. Given two agent runs at once, When both sync, Then the result is the same as one (type: edge)
  5. Given the configuration, Then the mailbox id and the cadence come from settings, not from constants in the code (type: happy)
