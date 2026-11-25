---
intent: INT-010
feature: label-prefix-removal
---

# U-label-prefix-removal-09: Cleanup use case: the cycle, the lease, the daily notice and the deleted-label record

- Component: mail-triage agent
- Layer: backend
- Contract: A use case runs in the mail cycle, one delete per cycle, under a single-writer lease; it reads the labels, the filters and the settings, applies the unit-08 rule, calls the unit-07 adapter, writes `deleted_label` and `label_empty_since`, and sends one Telegram message per day with counts.
- Note: unit 08 found that `label_empty_since` has no column for the waiting time a timer started with, so a lowered waiting time cannot keep running timers on their old length across a restart (AC 24, T16). Migration 0030 is unreleased, so this unit edits it in place: an additive `wait_minutes smallint NOT NULL` (5..720) on `categories.label_empty_since`, the model column, the store writing `Decision.wait` in `start_timer` and `StoredTimer.with_wait` reading it, with its migration tests.
- Files: `agents/mail-triage/migrations/versions/0030_label_boundary.py`, `agents/mail-triage/app/db/models.py`, `agents/mail-triage/app/db/pg_label_cleanup.py`, `agents/mail-triage/app/usecases/label_cleanup.py`, `agents/mail-triage/app/runner.py`, `agents/mail-triage/app/wiring.py`, tests under `agents/mail-triage/tests/`
- Depends on: U-label-prefix-removal-05, U-label-prefix-removal-07, U-label-prefix-removal-08
- Parallel: no
- Guardrails: guardrail-python, guardrail-pytest, guardrail-telegram
- Criteria:
  1. Given two overlapping cycles, When both run, Then only one deletes a label and none deletes it twice (lease). (type: security)
  2. Given three empty labels past their wait, When a cycle runs, Then exactly one is deleted (AC 7). (type: happy)
  3. Given a re-sort targeting a label, When a cycle runs, Then that label is not deleted. (type: security)
  4. Given a delete, When recorded, Then `deleted_label` holds the name for the retention period and the audit holds counts and a hash of the id (AC 29). (type: happy)
  5. Given the daily notice, When sent once a day, Then it holds counts only, and a canary label name is absent from every log, audit row, notice and error (AC 29). (type: security)
  6. Given `label_migration` is not `done`, When a cycle runs, Then nothing is deleted. (type: security)
  7. Given a lowered waiting time and a running timer, When the agent restarts, Then the timer keeps the waiting time it started with (AC 24). (type: edge)
  8. Given retention days passed, When the cycle runs, Then `deleted_label` and `label_rename_item` rows older than the retention are purged (spec R7, ADR-0061). (type: happy)
  9. Given a delete refused by the adapter, When the cycle goes on, Then the other steps still run and the timer stays. (type: error)
