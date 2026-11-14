---
intent: INT-003
feature: mail-triage-backlog
spec: docs/specs/mail-triage-backlog.md
---

# mail-triage-backlog

Overview of the plan: what is built, in which order and what can run in parallel. A builder reads only its own unit file (linked in the table) plus this index when it needs the dependencies.

## Units

| Unit | Name | Layer | Depends on | Parallel | Wave |
|---|---|---|---|---|---|
| [U-backlog-01](U-backlog-01.md) | Catch-up state table and backlog flag | backend (database) | — | yes | 1 |
| [U-backlog-02](U-backlog-02.md) | Store methods for the catch-up | backend (persistence) | U-01 | no | 1 |
| [U-backlog-03](U-backlog-03.md) | Budget remaining | backend | — | yes | 1 |
| [U-backlog-04](U-backlog-04.md) | Gmail lists unread inbox mail before a cut-off | backend (adapter) | — | yes | 1 |
| [U-backlog-05](U-backlog-05.md) | Share the decision step (refactor, no behaviour change) | backend | — | yes | 1 |
| [U-backlog-06](U-backlog-06.md) | Overview lists old urgent mail | backend | — | yes | 1 |
| [U-backlog-07](U-backlog-07.md) | CatchUp use case: flow, order, skip and finish | backend (use case) | U-02, U-03, U-04, U-05 | no | 1 |
| [U-backlog-08](U-backlog-08.md) | CatchUp use case: budget and reserve | backend (use case) | U-07 | no | 1 |
| [U-backlog-09](U-backlog-09.md) | CatchUp use case: alert cap | backend (use case) | U-08 | no | 1 |
| [U-backlog-10](U-backlog-10.md) | Run the catch-up in the mail cycle | backend (wiring) | U-07, U-08, U-09 | no | 1 |
| [U-backlog-11](U-backlog-11.md) | End-to-end replay and runbook | backend (test) and docs | U-10 | no | 1 |

## Build order

1. Wave 1 — in parallel: U-backlog-01, U-backlog-03, U-backlog-04, U-backlog-05, U-backlog-06; one at a time: U-backlog-02, U-backlog-07, U-backlog-08, U-backlog-09, U-backlog-10, U-backlog-11

All code lives in the existing component `agents/mail-triage` (Python, no UI). Each unit gets its own git worktree and branch (`feat/mail-triage-backlog-<nn>-<slug>`) and is built test-first: a failing test is shown before the implementation. A test is named after its criterion: `test_given_<x>_when_<y>_then_<z>`.

Common guardrails for every unit: `guardrail-python`, `guardrail-pytest`. Others are listed per unit. Commit bodies carry `Refs: INT-003`.

## Order and parallelism

```text
U-01 migration + models ──► U-02 store methods ──────────────┐
U-03 budget remaining() ─────────────────────────────────────┤
U-04 Gmail list_unread_before ───────────────────────────────┼─► U-07 CatchUp: flow ─► U-08 budget + reserve ─┐
U-05 extract decide_outcome (refactor) ──────────────────────┘                       └► U-09 alert cap ───────┤
U-06 overview: old urgent section ───────────────────────────────────────────────────────────────────────────┤
                                                                                                              ▼
                                                                         U-10 runner + wiring ─► U-11 end-to-end + runbook
```

U-01, U-03, U-04, U-05 and U-06 share no files and can be built in parallel. U-02 follows U-01. U-07 needs U-02, U-03, U-04 and U-05. U-08 and U-09 both change `catchup.py`, so they run one after the other (U-08 first).

## Units with a suffixed id (not split into files)

## Traceability: criteria to units

| Criterion | Unit(s) | Criterion | Unit(s) |
| --- | --- | --- | --- |
| AC-B1 | 04, 07, 11 | AC-B9 | 04, 07 |
| AC-B2 | 04, 11 | AC-B10 | 02, 06, 09, 11 |
| AC-B3 | 04, 07, 11 | AC-B11 | 09 |
| AC-B4 | 02, 07, 10 | AC-B12 | 07 |
| AC-B5 | 02, 07, 11 | AC-B13 | 07, 11 |
| AC-B6 | 07 | AC-B14 | 09 |
| AC-B7 | 08, 10, 11 | AC-B15 | 03, 08, 10, 11 |
| AC-B8 | 08 | | |

Every criterion of the spec is covered by at least one unit. The migration (U-01) has no spec criterion of its own: it is the base for AC-B4 and AC-B5.

## Done when

All units are merged through their own pull requests, the full suite is green with coverage of at least 90%, `/sdlc:verify` is green, and the end-to-end check in the runbook (check 9) passes against Marco's real mailbox.

## QA review (phase 4): additions to the criteria above

The `qa-strategist` agent reviewed this plan on 2026-11-08. Its findings are part of the units; where a unit above is vaguer than this section, this section wins.

**U-01.** Seed mails at revision 0002 before the upgrade (not an empty table). A second `catchup_state` row is impossible (check constraint `id = 1`).

**U-02.** `complete_backlog` twice goes through the real database and the alert stays unique. `backlog_alerts()` also counts alerts that are held, open, snoozed or closed (all states). Two concurrent `start_catchup` calls leave one row and the first `started_at`.

**U-03.** With an injected `today` that moves from 23:59:59 to 00:00:00 UTC, `remaining()` returns the fresh limit and never a negative value.

**U-04.** A mail exactly at the cut-off epoch is excluded (`before:` is exclusive). A timezone-aware cut-off becomes UTC epoch seconds; a naive datetime is rejected. Pagination with a third page that has a `nextPageToken` and an empty last page. The `-in:sent` part is in the query; the plan's earlier "SENT label in the result" criterion is replaced by a test on the real query string, plus the existing `OWN_MAIL` check on fetched mail. `FetchedMail.labels` is added and filled from `labelIds`.

**U-07.** Added criteria: (a) a mail that is no longer INBOX+UNREAD after fetch is skipped without a failure count and without a label; (b) several unread mails in one thread are all filed, each with its own label; (c) the normal pipeline files mail X after the catch-up listed it: `claim` is `DONE`, the mail is not judged again and no second alert exists; (d) the first 20 are the first 20 of the list, in order, not just a count; (e) `finish_catchup` is not called while a mail is `PENDING` or waiting for a retry; (f) an abandoned mail that Gmail still lists does not block `finish_catchup`; (g) the log and the audit log never contain a sentinel string that sits in the mail body (checked with `caplog`); (h) two overlapping `run_once` calls on the real PostgreSQL judge each mail once.

**U-08.** Boundary pair: with 52 remaining one mail is judged, with 51 none. One mail may cost two calls (small model, then large), so the `+2` is tested. The pipeline and `CatchUp` share one real `DailyBudget` with limit 60: after the pipeline spent 10, no catch-up mail is judged. The "next day" test moves the injected `today`, it does not stub `remaining`. When the day rolls over mid-run, the catch-up continues with the fresh budget.

**U-09.** Boundary pair: with 4 existing alerts the fifth urgent mail gets an alert and the sixth does not. "Newest five" holds across two runs of 20. A held alert (quiet hours) counts toward the cap, and its stored state is `held`. The injection test uses a fake judge that calls all eight mails urgent and bodies saying "ignore previous instructions": exactly five alerts.

**U-06.** An urgent mail filed without an alert is listed once and is not listed again in the next day's overview (C-B5).

**U-10.** Criterion 4 starts from a real store that has a history position and no `catchup_state` row. The step order is asserted with a recording fake. When the pipeline step raises, the catch-up step still runs (each step is guarded).

**U-11 is split.** U-11a: the end-to-end test, with a controllable clock (day 2, UTC midnight, an urgent mail inside quiet hours 23:00-07:00) and a new mail injected in the middle of a cycle, not only between days. U-11b: the runbook check 9 and the review record `docs/reviews/mail-triage-backlog.md` (documentation only). The log and audit search moved into U-07 (g).

**All units.** Time only through the injected `now` and `today`; no `sleep`; fixed epoch values. After the build, a mutation run (`mutmut`) on `catchup.py` and `decide_outcome` for the budget and cap comparisons (`<`, `<=`, the `+2`, the `5`) if `mutmut` is available; otherwise boundary-pair tests stand in for it and the review record says so.
