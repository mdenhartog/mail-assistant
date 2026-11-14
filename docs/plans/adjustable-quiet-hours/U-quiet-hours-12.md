---
intent: INT-002
feature: adjustable-quiet-hours
---

# U-quiet-hours-12: Policy snapshot in delivery, snooze and triage

- Layer: backend
- Contract: `AlertDelivery`, `SnoozeService` and `Triage` take a `TimePolicy` snapshot per operation from `PolicySource`; a held alert gets `release_at` (next quiet end under the snapshot) and is released when `now >= release_at`; a snooze that becomes due inside quiet hours is held and released at the quiet end valid then.
- Files: `app/usecases/deliver_alerts.py`, `app/usecases/snooze.py`, `app/usecases/triage.py`, `app/db/pg_store.py`, `tests/usecases/test_deliver_alerts.py`
- Depends on: U-quiet-hours-03, U-quiet-hours-04, U-quiet-hours-06a, U-quiet-hours-08
- Parallel: yes (with U-13)
- Guardrails: guardrail-sqlalchemy-alembic
- Criteria:
  1. Given a stored change, When the next alert arises, Then it is judged with the new values (AC-22) (type: happy).
  2. Given zone America/New_York and quiet hours 23:00-07:00, When an urgent mail arrives at 23:30 New York time, Then its alert is held (AC-23) (type: happy).
  3. Given a snoozed alert, When a change is stored, Then its due moment does not move (AC-24) (type: edge).
  4. Given an alert held at 02:00 with release 07:00, When quiet hours become 23:00-05:00 at 03:00, Then it is still released at 07:00; an alert held after the change uses the new hours (AC-25) (type: edge).
  5. Given a snooze due inside the new quiet hours, When it falls due, Then it is held and released at that quiet end (AC-26) (type: edge).
  6. Given a `PolicySource` fake that returns a different policy on its second call, When one operation runs, Then the whole operation used the first snapshot (type: edge).
