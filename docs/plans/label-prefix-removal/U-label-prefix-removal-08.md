---
intent: INT-010
feature: label-prefix-removal
---

# U-label-prefix-removal-08: Cleanup decision: the pure delete rule and the timer store

- Component: mail-triage agent
- Layer: backend
- Contract: A pure `core/label_cleanup.py` decides, per label and per check, one of `keep`, `start_timer`, `reset_timer`, `wait`, `delete`, from: system or not, in list or setting, child, counts, filter, protection period, timer age and the gap between checks. `db/pg_label_cleanup.py` stores `label_empty_since`.
- Files: `agents/mail-triage/app/core/label_cleanup.py`, `agents/mail-triage/app/db/pg_label_cleanup.py`, tests under `agents/mail-triage/tests/core/` and `agents/mail-triage/tests/db/`
- Depends on: U-label-prefix-removal-02, U-label-prefix-removal-03
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given any input with a count above 0, a system label, a label in the list or a filter target, When decided, Then the result is never `delete` (property test). (type: security)
  2. Given an empty label for the whole waiting time and no other blocker, When decided, Then the result is `delete` (AC 7). (type: happy)
  3. Given an empty label before the waiting time has passed, When decided, Then `wait` (AC 10). (type: security)
  4. Given a mail that arrived within the wait, When decided, Then `reset_timer` and the stored time is cleared (AC 10a). (type: edge)
  5. Given a timer started at T0 and a restart at T0 plus 3 hours, When decided, Then the timer is kept; given a gap of more than 3 cycles, Then it resets (AC 23). (type: edge)
  6. Given a lowered waiting time, When decided, Then running timers keep their length (AC 24). (type: edge)
  7. Given a label that left the list less than the protection period ago, When decided, Then `keep` (AC 28). (type: security)
  8. Given an empty parent with an empty child, When decided, Then the child goes first and the parent a cycle later after its own timer (AC 10c). (type: edge)
