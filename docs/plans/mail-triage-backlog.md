---
feature: mail-triage-backlog
spec: docs/specs/mail-triage-backlog.md
design: docs/design/mail-triage-backlog-design.md
threat-model: docs/security/mail-triage-threat-model.md (delta INT-003)
intent: INT-003
status: draft
date: 2026-11-08
---

# Plan: mail-triage-backlog

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

## Units

### U-backlog-01: Catch-up state table and backlog flag
- Layer: backend (database)
- Contract: migration `0003` creates `catchup_state(id int pk, started_at timestamptz not null, finished_at timestamptz null)` and adds `mail_item.backlog boolean not null default false`; models `CatchupState` and `MailItem.backlog`. The migration upgrades and downgrades cleanly and keeps existing rows.
- Files: `migrations/versions/0003_catch_up.py`, `app/db/models.py`, `tests/db/test_migrate.py`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-sqlalchemy-alembic
- Criteria:
  1. Given a database at revision 0002 with mail items, When the migration runs, Then `catchup_state` exists and every existing mail has `backlog = false` (type: happy).
  2. Given revision 0003, When the migration is downgraded, Then the table and the column are gone and the other data is unchanged (type: edge).
  3. Given a fresh database, When all migrations run, Then the model metadata matches the schema (no drift) (type: happy).

### U-backlog-02: Store methods for the catch-up
- Layer: backend (persistence)
- Contract: on `PgStore`: `catchup_state() -> CatchupState | None`, `start_catchup(at)` (idempotent: a second call keeps the first `started_at`), `finish_catchup(at)`, `complete_backlog(message_id, outcome)` (same as `complete` and sets `backlog = true`), `backlog_alerts() -> int` (alerts whose mail has `backlog = true`, any state).
- Files: `app/db/pg_store.py`, `tests/db/test_pg_store.py`
- Depends on: U-01
- Parallel: no
- Guardrails: guardrail-sqlalchemy-alembic
- Criteria:
  1. Given no row, When `catchup_state()` is read, Then it is `None` (type: happy).
  2. Given a started catch-up, When `start_catchup` is called again with a later time, Then `started_at` is unchanged (type: edge; AC-B4, AC-B5).
  3. Given a started catch-up, When `finish_catchup` runs, Then the state has `finished_at` and survives a new store instance (type: happy; AC-B5).
  4. Given a mail and an outcome with an alert, When `complete_backlog` runs, Then the mail has `backlog = true` and exactly one alert row exists (type: happy).
  5. Given two backlog alerts and one normal alert, When `backlog_alerts()` is read, Then it returns 2 (type: edge; AC-B10).
  6. Given `complete_backlog` is called twice for the same mail, When the second call runs, Then there is still one alert (type: error; AC-B5).

### U-backlog-03: Budget remaining
- Layer: backend
- Contract: `DailyBudget.remaining() -> int`, read-only (never spends), resets with the date like `try_spend`.
- Files: `app/adapters/judge_anthropic.py`, `tests/adapters/test_judge_anthropic.py`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-llm
- Criteria:
  1. Given a budget of 5 and 2 calls spent, When `remaining()` is read, Then it is 3 and a second read is still 3 (type: happy).
  2. Given all calls are spent, When `remaining()` is read, Then it is 0 (type: edge).
  3. Given the date changes, When `remaining()` is read, Then it is the full limit again (type: edge).

### U-backlog-04: Gmail lists unread inbox mail before a cut-off
- Layer: backend (adapter)
- Contract: `GmailReader.list_unread_before(cutoff: datetime) -> list[str]`: ids of mails with labels INBOX and UNREAD, query `before:<epoch seconds> -in:sent`, newest first (Gmail's own order), all pages. Read-only; no new scope. Mails carrying the agent's own `SENT` label are left out (`OWN_MAIL`).
- Files: `app/adapters/gmail_read.py`, `tests/adapters/test_gmail_read.py`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-gmail, guardrail-api-client
- Criteria:
  1. Given a cut-off, When the list is requested, Then the request uses labels INBOX and UNREAD and a `before:` query in epoch seconds (type: happy; AC-B1).
  2. Given two result pages, When the list is requested, Then the ids of both pages come back in Gmail's order (type: happy; AC-B9).
  3. Given a mail with the `SENT` label in the result, When the list is requested, Then it is not returned (type: security; AC-B2).
  4. Given a rate-limit error on a page, When the list is requested, Then it is retried with backoff like other reads (type: error).
  5. Given no matching mail, When the list is requested, Then an empty list is returned (type: edge).
  6. Given the wrapper, When its public methods are inspected, Then it still has no trash, delete or spam operation (type: security; AC-B3, SC-14).

### U-backlog-05: Share the decision step (refactor, no behaviour change)
- Layer: backend
- Contract: `decide_outcome(verdict, mail, known_labels, now) -> Outcome` becomes a module-level function in `app/usecases/triage.py`; `TriagePipeline` calls it. No new parameter, no flag. This is a pure refactor: the existing tests stay green and are not edited.
- Files: `app/usecases/triage.py`, `tests/usecases/test_triage.py` (one added test)
- Depends on: —
- Parallel: yes
- Guardrails: —
- Criteria:
  1. Given a judgement, When `decide_outcome` is called directly, Then it returns the same outcome as the pipeline produced before (type: happy).
  2. Given a `NeedsAttention` verdict, When `decide_outcome` is called, Then the label is `Assistant/Other`, urgent, with the same note as before (type: edge).
  3. Given the full existing test suite of the pipeline, When it runs, Then every test passes unchanged (type: regression).

### U-backlog-06: Overview lists old urgent mail
- Layer: backend
- Contract: `FiledMail` gets `urgent: bool`; `PgStore.filed_without_alert_since` fills it; `build_overview` adds the section "Old mail that looked urgent" (at most 10 lines, then "…and n more"), escaped and capped like the existing sections, only for mails filed without an alert and urgent. Counts per category are unchanged.
- Files: `app/usecases/overview.py`, `app/db/pg_store.py`, `tests/usecases/test_overview.py`, `tests/db/test_pg_store.py`
- Depends on: —
- Parallel: yes (U-02 also edits `pg_store.py`; merge in order U-02, U-06)
- Guardrails: guardrail-telegram
- Criteria:
  1. Given urgent mails filed without an alert, When the overview is built, Then they appear in the new section with sender and subject (type: happy; AC-B10).
  2. Given no urgent mail without an alert, When the overview is built, Then the section is absent and the text equals today's text (type: edge).
  3. Given a subject with markup, When the section is built, Then it is escaped and capped (type: security; SC-7).
  4. Given more than 10 such mails, When the overview is built, Then 10 are listed, the rest is counted and the message stays within the Telegram limit (type: edge).
  5. Given the store, When `filed_without_alert_since` runs, Then `urgent` is true only for urgent mails (type: happy).

### U-backlog-07: CatchUp use case: flow, order, skip and finish
- Layer: backend (use case)
- Contract: `CatchUp(mailbox, judge, store, notifier, budget, now).run_once() -> RunSummary`. On the first call it stores the cut-off (`start_catchup(now)`); a finished catch-up returns at once. Each run lists the mails (U-04), takes at most `RUN_LIMIT = 20` unfinished mails in the listed order (newest first), fetches, claims (`DONE`: skip), judges, decides (U-05), files and calls `complete_backlog`. When every listed mail is done and no retry is pending it calls `finish_catchup`. Failures use `record_failure`, `MAX_ATTEMPTS` and `notify_failure` like the pipeline.
- Files: `app/usecases/catchup.py`, `tests/usecases/test_catchup.py`
- Depends on: U-02, U-03, U-04, U-05
- Parallel: no
- Guardrails: guardrail-gmail, guardrail-llm
- Criteria:
  1. Given no catch-up state, When it runs, Then the cut-off is stored before any mail is touched (type: happy; AC-B4).
  2. Given three unread mails, When it runs, Then each is filed with one label and the inbox label is removed, in the listed (newest first) order (type: happy; AC-B1, AC-B9).
  3. Given a mail already filed earlier, When it runs, Then it is skipped and not judged (type: edge; AC-B6).
  4. Given 25 unread mails, When it runs once, Then 20 are processed and the catch-up is not finished (type: edge).
  5. Given nothing is left, When it runs, Then the catch-up is finished and a second `run_once` does nothing and calls neither the mailbox nor the judge (type: happy; AC-B5).
  6. Given a finished catch-up, When the agent is rebuilt (new store, new use case), Then it still does nothing (type: edge; AC-B5).
  7. Given a mail that fails three times, When it runs repeatedly, Then it is abandoned with one notice and the next mail is processed (type: error; AC-B12).
  8. Given the model is down, When it runs, Then the run stops, nothing is filed wrongly and the catch-up is not finished (type: error).
  9. Given the mailbox port, When the catch-up runs, Then it only calls list, fetch, ensure-label and file, never a delete (type: security; AC-B3).
  10. Given any run, When logs are inspected, Then they hold counts and ids only (type: security; AC-B13).

### U-backlog-08: CatchUp use case: budget and reserve
- Layer: backend (use case)
- Contract: before each mail `CatchUp` stops for the day when `budget.remaining() < BUDGET_RESERVE + 2` (`BUDGET_RESERVE = 50`; two calls cover the small and the large model). As a second guard it also stops, without filing, if the verdict is `NeedsAttention("budget")`. A stopped run leaves the mail untouched in the inbox and does not finish the catch-up.
- Files: `app/usecases/catchup.py`, `tests/usecases/test_catchup.py`
- Depends on: U-07
- Parallel: no
- Guardrails: guardrail-llm
- Criteria:
  1. Given a remaining budget of 51 or less, When it runs, Then no mail is judged and none is touched (type: happy; AC-B8, AC-B15).
  2. Given a remaining budget of 52 and three mails, When it runs, Then the first mail is judged and the run stops once fewer than 52 remain (type: edge; AC-B15).
  3. Given the budget is used up, When it runs, Then no mail is labelled `Assistant/Other` and no alert is created (type: security; AC-B8, T-23).
  4. Given the next day (budget restored), When it runs, Then it continues with the remaining mails (type: happy; AC-B8).
  5. Given the judge still returns `NeedsAttention("budget")`, When it runs, Then the mail is not filed and the run stops (type: error; AC-B8).
  6. Given new mail and old mail in the same cycle, When the pipeline runs first and uses the budget, Then the catch-up only gets what is above the reserve (type: edge; AC-B7, AC-B15).

### U-backlog-09: CatchUp use case: alert cap
- Layer: backend (use case)
- Contract: an urgent old mail gets its alert (state from the shared `decide_outcome`, so quiet hours still apply) only while `store.backlog_alerts() < BACKLOG_ALERT_LIMIT` (5). At the limit the outcome is stored with `alert=None` (still `urgent = true`), so the overview lists it (U-06).
- Files: `app/usecases/catchup.py`, `tests/usecases/test_catchup.py`
- Depends on: U-08
- Parallel: no
- Guardrails: guardrail-telegram
- Criteria:
  1. Given seven urgent old mails, When the catch-up runs, Then exactly five alerts exist, for the five newest (type: happy; AC-B10).
  2. Given the two other urgent mails, When they are filed, Then they are filed urgent without an alert (type: happy; AC-B10).
  3. Given five alerts from an earlier run and a restart, When another urgent old mail is judged, Then no sixth alert is created (type: edge; AC-B10, T-24).
  4. Given an urgent old mail inside quiet hours, When it gets an alert, Then it is held until the quiet hours end (type: edge; AC-B11).
  5. Given an injected mail that the model calls urgent, When the cap is reached, Then no extra alert follows (type: security; AC-B14).

### U-backlog-10: Run the catch-up in the mail cycle
- Layer: backend (wiring)
- Contract: `Runner` gets a `CatchUpPort` and one `_guard("catchup", ...)` step after `pipeline`; `wiring.build` constructs `CatchUp` with the existing mailbox, judge, store and the same `DailyBudget` instance. A failing catch-up never stops the other steps.
- Files: `app/runner.py`, `app/wiring.py`, `tests/test_runner.py`, `tests/test_wiring.py`
- Depends on: U-07, U-08, U-09
- Parallel: no
- Guardrails: —
- Criteria:
  1. Given a mail cycle, When it runs, Then the order is release, pipeline, catch-up, deliver, overview, purge (type: happy; AC-B7).
  2. Given the catch-up raises, When the cycle runs, Then the later steps still run and the heartbeat is touched (type: error).
  3. Given the wiring, When the judge and the catch-up are built, Then they share one `DailyBudget` (type: edge; AC-B15).
  4. Given an installation with a stored history position and no catch-up state, When the agent starts, Then the catch-up starts without any setting or command (type: happy; AC-B4).

### U-backlog-11: End-to-end replay and runbook
- Layer: backend (test) and docs
- Contract: an end-to-end test on the existing real-PostgreSQL harness with fake Gmail, Telegram and Anthropic that replays 2026-11-08: 75 unread mails (some urgent), a budget of 200 and the reserve of 50, over two simulated days with new mail arriving in between. The runbook `docs/reviews/mail-triage-e2e.md` gets a catch-up check (check 9) and `docs/reviews/mail-triage-backlog.md` is created as the review record.
- Files: `tests/db/test_catch_up_end_to_end.py`, `docs/reviews/mail-triage-e2e.md`, `docs/reviews/mail-triage-backlog.md`
- Depends on: U-10
- Parallel: no
- Guardrails: guardrail-pytest
- Criteria:
  1. Given 75 unread old mails and the budget, When the cycles run, Then every old mail has one label and left the inbox within two days and no mail was deleted or sent (type: happy; AC-B1, AC-B3).
  2. Given new mail arriving each cycle, When the catch-up runs, Then every new mail is handled in its own cycle (type: happy; AC-B7, AC-B15).
  3. Given more than five urgent old mails, When it finishes, Then five alerts were sent and the rest sit in the next overview (type: happy; AC-B10).
  4. Given a restart in the middle of the catch-up, When it resumes, Then no mail is processed twice and no second catch-up starts (type: edge; AC-B5).
  5. Given read mail and mail outside the inbox in the fake mailbox, When it finishes, Then none of it changed (type: security; AC-B2).
  6. Given the log output and the audit log, When they are searched for mail text, Then nothing is found (type: security; AC-B13).

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
