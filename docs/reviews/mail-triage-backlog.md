---
feature: mail-triage-backlog
intent: INT-003
spec: docs/specs/mail-triage-backlog.md
plan: docs/plans/mail-triage-backlog.md
status: built
date: 2026-11-08
---

# Review record: one-time catch-up of unread inbox mail

## What was built

All eleven units of the plan (U-01 to U-11), test first, on the branch `feat/mail-triage`, one commit per unit with `Refs: INT-003`. The catch-up is a new use case (`app/usecases/catchup.py`) that runs after the normal pipeline in every mail cycle. It files the unread inbox mail that was there before the cut-off, newest first, with the same judging and labels as new mail.

## Gates

| Gate | Result |
| --- | --- |
| Intent confirmed by the originator | INT-003, confirmed by Marco on 2026-11-08 |
| Spec approved | `mail-triage-backlog.md`, approved by Marco; the reserve of 50 calls (C-B4, AC-B15) added in phase 3 and approved by Marco |
| Threat model (delta T-18 to T-27) approved | approved by Marco |
| Design and ADR-0021 approved | approved by Marco |
| Plan reviewed by `qa-strategist` | done; findings added to the plan (section "QA review") |
| Tests first, shown red before green | every unit |
| Full suite, coverage | all tests green, coverage 98 % (floor 90 %) |
| Lint and types | `ruff` clean on `app`, `tests` and `migrations`; `pyright` 0 errors on `app` |
| Manual mutation check on `catchup.py` | 9 hand-made mutations of the budget, cap, run limit and guards: all caught (one, the value of the run limit, was caught only after a literal test was added) |
| Check against the real mailbox | **not yet run**: see "Open" |

## Criteria to tests

| Criterion | Where it is tested |
| --- | --- |
| AC-B1, AC-B9 | `test_catchup.py` (order, one label), `test_catch_up_end_to_end.py` |
| AC-B2 | `test_gmail_read.py` (query), `test_catchup.py` (read or moved after listing), end-to-end (read, archived mail untouched) |
| AC-B3 | `test_gmail_read.py` (source has no delete), `test_catchup.py` (only list, fetch, label, file), end-to-end (nothing sent) |
| AC-B4 | `test_catchup.py`, `test_catchup_wiring.py` (a running installation starts it by itself) |
| AC-B5 | `test_pg_store.py`, `test_catchup.py` (finished, rebuilt), end-to-end (restart) |
| AC-B6, AC-B7 | `test_catchup.py` (already filed, filed by the pipeline meanwhile), `test_runner.py` (order), end-to-end |
| AC-B8, AC-B15 | `test_catchup.py` (boundary pair 51/52, two calls per mail, next day, midnight), `test_catchup_wiring.py` (shared budget) |
| AC-B10, AC-B11, AC-B14 | `test_catchup.py` (cap, restart, held alerts count, injection), `test_pg_store.py`, `test_overview.py`, end-to-end |
| AC-B12 | `test_catchup.py` (abandon, not blocking the finish, fetch failure) |
| AC-B13 | `test_catchup.py` (sentinel in the logs), end-to-end (sentinel in logs and audit log) |

## Decisions that differ from the plan

- **One branch instead of one worktree per unit.** Marco asked for everything on one new branch (`feat/mail-triage`), so the units were built one after the other as separate commits on it.
- **The overlapping-run test of the QA review was not written.** The agent holds a single-replica lock and the cycle awaits each run, so two runs cannot overlap; `claim()` returning `PENDING` for a claimed but unfinished mail is crash recovery by design. If more than one replica is ever allowed, this needs its own design and test.
- **`mutmut` was not used** because it is not installed and adding a dependency needs a decision; a manual mutation check on the sensitive comparisons stands in for it.
- **`build_runner` got an optional `today` argument** so the budget clock can be controlled in tests; production passes nothing.
- **The `INT` number is 003, not 002.** `INT-002` already exists on the branch `docs/mail-triage-spec` (adjustable quiet hours, draft); that branch is merged into this one.

## Open

- Run check 9 of `docs/reviews/mail-triage-e2e.md` against Marco's real mailbox (and confirm the old unread mail is labelled).
- The daily budget counter is in memory (as before), so a restart resets today's count and the reserve of 50 holds again only from the next day (ADR-0021).
- Persisting the budget count, if that restart gap matters, is a separate change.
