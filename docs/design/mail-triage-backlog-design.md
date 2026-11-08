---
feature: mail-triage-backlog
spec: docs/specs/mail-triage-backlog.md
intent: INT-003
status: approved
date: 2026-11-08
---

# Design: one-time catch-up of unread mail

Extends `docs/design/mail-triage-design.md`. Only what changes is described here. No new component, no new external system, no new Gmail scope.

## Idea in one paragraph

A new use case `CatchUp` runs inside the existing mail cycle, right after the normal pipeline. It lists the unread inbox mails that are older than a stored cut-off time, newest first, and files them through the same judge, labels and alert path as new mail, with three differences that make it safe: it stops for the day when the model budget (minus a reserve for new mail) is used up, it creates at most 5 alerts in total, and it records its progress in one small table so that it runs exactly once.

```
mail_cycle:  release_due → pipeline.run_once (new mail, unchanged)
                         → catchup.run_once  (NEW)  → deliver alerts → overview → purge
catchup.run_once:
  state = store.catchup_state()            none → start now (cut-off = now); done → return
  ids   = mailbox.list_unread_before(cut-off)          newest first, own sent mail excluded
  for id in ids, up to RUN_LIMIT (20) per run:
      stop if budget.remaining() < RESERVE + 2         → leave the rest for tomorrow
      fetch (no longer INBOX+UNREAD: skip) → claim (DONE: skip) → judge → decide (shared) → cap alerts → file → complete_backlog
  nothing left to do and no retry pending  → store.finish_catchup()
```

## Why the cut-off and no stored list

Gmail already is the list: a filed mail loses its inbox label, so the next query ("INBOX + UNREAD, before:<cut-off>") returns only what is still waiting. The only things to remember are *when the catch-up started* (so mail that arrives later stays "new mail") and *whether it finished*. This avoids copying 75 message ids into the database and cannot drift from the mailbox.

## Changes by part

| Part | Change |
| --- | --- |
| `usecases/catchup.py` (new) | `CatchUp` with `run_once()`; constants `BACKLOG_ALERT_LIMIT = 5`, `RUN_LIMIT = 20`, `BUDGET_RESERVE = 50`. Depends on the ports `Mailbox`, `Judge`, `CatchUpStore`, `BudgetView` only. |
| `usecases/triage.py` | `TriagePipeline._decide` becomes a module-level function `decide_outcome(verdict, mail, known_labels, now)` that both the pipeline and `CatchUp` call. The pipeline's behaviour does not change. No flag is added to it. |
| `adapters/gmail_read.py` | New `list_unread_before(cutoff)`: `messages.list` with labelIds INBOX and UNREAD and query `before:<epoch seconds> -in:sent`, newest first, all pages. The cut-off must be timezone-aware (converted to UTC epoch seconds). `FetchedMail` gets the field `labels` (Gmail already returns `labelIds`), so the catch-up can see that a mail was read or moved after listing. Read-only; no new scope. |
| `adapters/judge_anthropic.py` | `DailyBudget.remaining()` (read-only). The judge is not changed. `CatchUp` checks the budget **before** it asks, so "budget out" never reaches the judge as `NeedsAttention("budget")` (spec AC-B8). As a second guard `CatchUp` also stops if a verdict still says `needs_attention:budget`. |
| `db/models.py`, migration `0003` | Table `catchup_state` (`id`, `started_at`, `finished_at` nullable; one row). Column `mail_item.backlog` boolean, default false. |
| `db/pg_store.py` | `catchup_state()`, `start_catchup(at)`, `finish_catchup(at)`, `complete_backlog(message_id, outcome)` (sets `backlog`), `backlog_alerts()` (alerts whose mail is `backlog`). |
| `usecases/overview.py` | `FiledMail` gets `urgent: bool`. The overview adds a section "Old mail that looked urgent" (at most 10 lines, escaped like the others) for urgent mails filed without an alert. Counts per category stay as they are. |
| `runner.py` | New port `CatchUpPort` and one `_guard("catchup", ...)` step after `pipeline`. |
| `wiring.py` | Builds `CatchUp` with the same mailbox, judge, store and the same `DailyBudget` instance. |

## Decisions (my calls; Marco may change them)

1. **Budget reserve of 50 calls per day.** The daily budget is 200. The catch-up may use only the calls above a reserve, so it never takes the budget that a mail arriving later today needs. 75 mails need about 75 to 150 calls, so the catch-up finishes in one or two days. The reserve is a constant in code, like the quiet hours (C7), not a setting.
2. **Alert cap counted in the database**, not in memory: `backlog_alerts() >= 5` means "no alert for this mail". It survives restarts. The mail is still filed with `urgent = true`, and the overview lists it.
3. **Newest first, at most 20 mails per run.** A run stays short and the one-minute cycle keeps serving new mail and Telegram.
4. **Abandoned or already filed mails stay listed** by Gmail (they are still unread in the inbox), so `CatchUp` skips them through `claim()` and counts them as done. The catch-up finishes when every listed mail is done, filed or abandoned.
5. **No ADR change to ADR-0014** (routing) or ADR-0018 (disclosure). A new ADR-0021 records the catch-up design (marker table, reserve, alert cap).

## Failure and restart behaviour

- Crash mid-mail: the mail was claimed but not completed, so the next run finds it as `PENDING` and handles it again (same as new mail).
- Restart: `catchup_state` says started and not finished, so the catch-up simply continues; finished means it never runs again.
- Gmail or Anthropic down: the same handling as new mail (`ModelUnavailable` stops the run, nothing is lost).
- The cut-off is stored before the first mail is touched, so a crash between the two cannot make the catch-up start again with a later cut-off.

## Test strategy (feeds phase 4)

Unit tests with fakes for `CatchUp` (order, stop at budget, alert cap, skip, finish, restart); store tests on a real PostgreSQL (testcontainers) for the marker, the counter and `complete_backlog`; a contract test for `list_unread_before` against a fake Gmail service (query string, own mail excluded, read mail excluded); an end-to-end test on the existing real-PostgreSQL harness with fake Gmail, Telegram and Anthropic that replays today's situation (75 unread, budget 200).

## Threat model link

All delta threats T-18 to T-27 map to the criteria AC-B1 to AC-B14; the reserve adds AC-B15 (see the spec).

## Changes after the QA review (phase 4)

- **Read or moved meanwhile.** After `fetch`, a mail that no longer carries both INBOX and UNREAD is skipped without a failure and without a label (spec AC-B2: read mail is never touched).
- **Budget is in memory.** `DailyBudget` lives in memory (as for the base spec AC-26), so a restart resets today's count and the reserve is then not guaranteed until the next day. This is an accepted limitation, recorded in ADR-0021; persisting the count is a separate change.
- **Concurrency.** Two overlapping runs (a slow run, or two replicas) must not judge a mail twice: `claim()` is the guard, and `start_catchup` is idempotent under a race. Tested on the real PostgreSQL.
- **Only one catch-up row.** A check constraint keeps `catchup_state` to one row (`id = 1`).
