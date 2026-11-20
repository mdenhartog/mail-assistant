---
intent: INT-004
spec: docs/specs/mail-categories.md
plan: docs/plans/mail-categories/index.md
pr: not opened yet (the work is on the branch feat/INT-004/mail-categories/r1; the spec, plan and ADRs are on docs/INT-004-mail-categories-spec)
release: not released
---

# Review record: mail categories (the list, the page "Categories" and "Review moves")

The feature lets the user keep their own list of categories in the web app and re-sort mail already filed after a change of the list, with a review before anything moves. It is built in 36 units, U-mail-categories-01 to U-mail-categories-36 (the index is `docs/plans/mail-categories/index.md`; the plan has no unit 00). Release R1 is the list and the page "Categories" (U-01 to U-11); release R2 is the plan, the review page, the apply and Move back (U-12 to U-19); U-20 to U-25 connect them to PostgreSQL, Gmail and Telegram; U-26 to U-34 are the fixes of the challenge and verify phases. Nothing is deployed and nothing is released. The documentation of phase 8 is this record and the [user guide](../user-guide/mail-categories.md).

## Gates

| Phase | Result | Evidence |
| --- | --- | --- |
| 1 Spec | Approved by the user, 2026-11-14 (D1 to D19, round table); revised afterwards: the web lock answers 401 and the sign-in page says how to unlock (AC-32, commit `ef7f9cb`) | `docs/specs/mail-categories.md` |
| 2 Threat model | Written; risks R-1 and MR-1 to MR-4 recorded; MR-4 accepted for R1 | `docs/security/mail-categories-threat-model.md` |
| 3 Design | Approved; ADR-0042 to ADR-0047 (category contract, mailbox id, api reads sender and subject, closed-set judging, plan lifecycle, decision functions and purge); ADR-0048 (pinned mail alerts) and ADR-0049 (worker egress limited by CIDR) came during the build | `docs/design/mail-categories-design.md`, `docs/memory/index.md` |
| 4 Plan | 36 units in 10 waves (wave 9 added after review and verify, wave 10 for the sender filter) | `docs/plans/mail-categories/index.md` |
| 5 Build, test first | Every unit built on `feat/INT-004/mail-categories/r1`, commits with `Refs: INT-004` and `Unit:` trailers. Exception: see "Test-first exception" below | `git log` of the branch |
| 6 Challenge | Findings fixed by U-26 to U-34, see "Challenge" | this file |
| 7 Verify | Run on a real prod-like stack, see "Verification results" | this file |
| 8 Finish | Spec, plan, user guide and this record on the docs branch; architecture model updated on the build branch (see "Architecture") | `node scripts/docs.mjs check` |
| 9 Release | Not started | the release checklists `docs/release/mail-categories-r1.md` and `docs/release/mail-categories-r2.md` on the build branch |

## Challenge

The challenge of phase 6 (red team RED, security review SEC, code review REV and the UX review) produced the findings below. The repository names five of them in a unit contract (RED-003, RED-004, RED-005, SEC-03, SEC-06); the other findings are traced here by the unit that fixed their topic, because the findings list itself is not in the repository.

| Unit | What it fixed | Finding ids |
| --- | --- | --- |
| U-26 Plan apply timing and the scheduling guard | The plan notice button kinds are allowed by `telegram_action`; a delayed plan is claimed only after its notice was sent; a cancel near the start follows the database clock; only `approve_plan` can schedule a plan or set `apply_after` (column grants plus a trigger guard, SQLSTATE 42501) | not named in the repository |
| U-27 Review fixes: archive label, names, authentication results, log redaction | The Archive label is matched case-insensitively in one helper; `..` is refused in names and a refused label files under "Other"; Authentication-Results is parsed as RFC 8601 and fails closed when ambiguous; mail headers are redacted from logs and error reports whatever their case; line and paragraph separators show as a space on the review page | RED-003, RED-004, RED-005, SEC-03, SEC-06 |
| U-28 Review fixes: hidden SQL parameters, debounce, retries, notice wording | Database errors hide statement parameters; the build debounce comes only from the settings; failed move attempts spread across apply runs; the delayed notice states the zone and names its buttons; the list notice shows every changed category first; a retried apply checks scope, archive and pinning again | not named in the repository |
| U-29 Review page wording and status | The loading text is a status; the move button says how many mails move and that only labels change; the approval dialog and the scheduled notice are reworded; the page shows when the mails moved and a plain reason for each one that did not; each group has a status chip and can be looked at before approving | UX items |
| U-30 Categories page leave guard and save bar | A question before leaving the page with unsaved changes; a sticky save bar on small screens that counts the unsaved changes; the save summary lists each change by name; the removed notice shows where the card was; clearer not-ready, older-category and limit texts with a Check again button | UX items |
| U-31 Worker HTTPS egress limited by CIDR | The worker's HTTPS egress rule carries CIDR exceptions (ADR-0049) | security review (egress) |
| U-32 Plan view: example, apply settings, moved count | The plan view carries an example mail per group, the threshold and delay of the apply, and the number of mails moved, so the review page and the approve summary can say them | review items |
| U-33 Last plan | The last plan is the plan that ended most recently (applied, cancelled or replaced) and names its end time | review items |
| U-34 Mutation gate | Mutation testing of the pure modules of INT-004 with a nightly workflow; surviving mutants were killed by new tests (scope, pinned, list_text, approval_text, resort_plan, category-policy) | REV items (test strength) |
| U-35 Sender filter and sort in the api | `POST /api/plan/items/search` takes the sender text in a body (never in a URL), with a closed sort set and a stable order; the sort is one literal SQL statement with bound parameters (semgrep `avoid-sqlalchemy-text` found a string-built version). | AC-58 |
| U-36 Sender search and sort on the review page | A labelled search field, a sort choice, a result count and "Select the mails that match", which decides exactly the matching ids. | AC-59 |

### Waiver REV-002

Two commits on the branch lack the `Unit:` trailer: `f6c4cb4` (threat model, design, ADRs 0042 to 0047 and the unit plan) and `71749c8` (the draft spec). The decision is to waive the finding and not to rewrite history, because rewriting shared history is riskier than a missing trailer. Both commits are documentation only and their content is covered by the spec and the plan.

### Test-first exception

The U-32 web tests for the group summary, the applied banner and the example line were written together with the code, not strictly red first. The backend side of U-32 was red first (`4591b4d` before `b0c3576`); the web side (`e974344`, `d99b6bf`, `cf3a92f`) was not. The tests exist and pass, but the red step is not shown by the commit order for those three.

## Acceptance criteria and their tests

The paths are relative to the build worktree. "Agent" is `agents/mail-triage/tests`, "Api" is `backend/tests`, "Web" is `apps/web/src`, "Policy" is `packages/category-policy/tests`. "E2E" are the Playwright specs in `apps/web/e2e`: `categories.spec.ts` (project `categories`), `review.spec.ts` (project `review`) and `ui-states.spec.ts` (stubbed api, all states at four widths).

| AC | Release | Tests |
| --- | --- | --- |
| AC-1 | R1 | Api `test_categories_api.py` (list with counts and Other); Web `features/categories/CategoriesPage.test.tsx`; E2E `categories.spec.ts` (page shows the list) |
| AC-2 | R1 | Policy `test_rules.py`, `test_contract_cases.py`, `test_properties.py` (one row per rule); Api `test_categories_api.py` (store, audit, 422 per rule, unchanged list); Web `features/categories/policy.test.ts`, `SaveCategories.test.tsx`; E2E `categories.spec.ts` (edit and save, refused values, save without change) |
| AC-3 | R1 | Api `test_categories_api.py` (stale version gives 409 with the current list); Web `SaveCategories.test.tsx`; E2E `categories.spec.ts` (conflict) |
| AC-4 | R1 | Api `test_categories_api.py` (the empty list: Other stays and cannot be deleted or renamed) |
| AC-5 | R1 | Agent `core/test_judgement_closed_set.py`; Agent `test_list_sync_labels.py` (no other `Assistant/` label is created) |
| AC-6 | R1 | Agent `usecases/test_judgement_triage.py`, `core/test_judgement_closed_set.py` |
| AC-7 | R1 | Agent `usecases/test_judgement_triage.py` (hostile model output goes to Other). The optional live-model evaluation of the spec is not built |
| AC-8 | R1 | Policy `test_rules.py`, `test_contract_cases.py` (50 passes, 51 refused); Web `features/categories/policy.test.ts`; Agent `core/test_judgement_closed_set.py` (more than 15 categories) |
| AC-9 | R2 | Agent `test_resort_build_flow.py`; E2E `review.spec.ts` |
| AC-10 | R2 | Agent `core/test_scope_classify.py`, `test_resort_build_scope.py` |
| AC-11 | R2 | Agent `test_resort_build_limits.py` with `fakes/budget_ledger.py` (fake clock and ledger, reserve, cap of 5 000) |
| AC-12 | R2 | Web `features/review/ReviewPage.test.tsx`, `ReviewItems.test.tsx` |
| AC-13 | R2 | Agent `db/test_plan_approval.py`, `db/test_plan_decision.py`, `test_resort_build_flow.py`; Api `test_plan_api.py` (decisions by group, by ids, approve); Web `ReviewPage.test.tsx`; E2E `review.spec.ts` (approving a group) |
| AC-14 | R2 | Agent `test_resort_apply_flow.py` (swaps the label and changes nothing else); `test_gmail_allowlist.py`; E2E `review.spec.ts` |
| AC-15 | R2 | Agent `test_resort_apply_flow.py` (mail changed meanwhile is skipped with a reason) |
| AC-16 | R2 | Agent `core/test_resort_plan.py` (a plan in building or ready is replaced and its decisions discarded); Web `features/review/ReviewRoute.test.tsx` (all plan states) |
| AC-17 | R2 | Agent `test_resort_build_flow.py`, `test_resort_apply_flow.py` (a label of a deleted category; empty labels named in the result notice) |
| AC-18 | R2 | Agent `test_resort_build_flow.py` (notice with numbers only) |
| AC-19 | R2 | Agent `db/test_plan_purge.py`, `core/test_resort_plan.py` |
| AC-20 | R1 | Agent `db/test_categories_grants.py`, `db/test_plan_grants.py` (SQLSTATE 42501 on a real PostgreSQL) |
| AC-21 | R2 | Web `CategoriesPage.test.tsx`, `ReviewItems.test.tsx` (markup shown as text); Api `test_categories_api.py`, `test_plan_api.py` (markup returned as text). The Content-Security-Policy header is the one of web-settings, covered by `backend/tests/test_edge_config.py` and `test_http_surface.py`; it is not re-tested per page |
| AC-22 | R1, R2 | Api `test_categories_api.py`, `test_plan_api.py` (no session 401, no token or wrong origin 403); E2E `categories.spec.ts` |
| AC-23 | R1, R2 | E2E `categories.spec.ts` and `review.spec.ts` (real stack, four widths, 200 % text, keyboard); E2E `ui-states.spec.ts` (every state, axe); Web `ProtectedShell.test.tsx`, `SaveCategories.test.tsx`, `ReviewPage.test.tsx`, `ReviewItems.test.tsx` |
| AC-24 | R2 | Web `features/review/ReviewItems.test.tsx` (1 000 items, pages of 100, Load more); Api `test_plan_api.py` (at most 100 per page). The bounds "within 1 second and under 1 500 DOM nodes" are not measured by a test |
| AC-25 | R1 | Agent `test_list_sync_labels.py`, `test_fakes_gmail.py` (created once, never filled) |
| AC-26 | R2 | Agent `test_resort_apply_flow.py` (a proposed category that left the list is skipped); `test_resort_apply_move_back.py` (move back restores labels outside the list) |
| AC-27 | R2 | Agent `db/test_plan_grants.py`, `db/test_plan_decision.py`; Api `test_plan_refusal.py` (SQLSTATE to 409 or 422) |
| AC-28 | R1 | Agent `test_gmail_allowlist.py` (reflection test against the allow-list) |
| AC-29 | R1, R2 | Agent `test_list_notice_text.py`, `test_list_notice_flow.py`, `core/test_approval_text.py` |
| AC-30 | R2 | Api `test_plan_api.py` (canaries in no log and no error body, no-store); Api `test_logging_hygiene.py`; E2E `categories.spec.ts` and `review.spec.ts` (canary in no log of the stack) |
| AC-31 | R1, R2 | Agent `test_list_notice_flow.py`, `test_runner_list_notice.py`, `db/test_pg_list_notice.py`; E2E `categories.spec.ts` (the list is stored for the agent). The result notice of an apply: `test_resort_apply_flow.py` |
| AC-32 | R1, R2 | Api `test_categories_api.py`, `test_plan_api.py` (401 under the lock; 409 for a stale plan id or count); Web `features/categories/CategoriesRoute.test.tsx`, `features/review/ReviewRoute.test.tsx`; E2E `categories.spec.ts` and `review.spec.ts` (sign-in page) |
| AC-33 | R1, R2 | Api `test_categories_api.py` (the eleventh save is 429); Agent `test_resort_build_limits.py`, `test_resort_build_debounce.py` (debounce with a fake clock) |
| AC-34 | R2 | Api `test_plan_api.py` (more than 200 ids refused, exactly 200 accepted, page size above 100 refused) |
| AC-35 | R2 | Agent `test_resort_apply_safety.py` (two runs at once, a repeat, a mail that gained Archive) |
| AC-36 | R1, R2 | Agent `test_list_notice_flow.py`, `db/test_plan_decision.py`; Api `test_categories_api.py` (audit record) |
| AC-37 | R1 | Agent `db/test_categories_repository.py`, `db/test_judgement_store.py` |
| AC-38 | R1 | Agent `core/test_judgement_closed_set.py`, `usecases/test_judgement_triage.py` |
| AC-39 | R1, R2 | Agent `core/test_judgement_pinned.py`, `core/test_pinned_tokeniser.py`, `usecases/test_judgement_triage.py`, `db/test_judgement_store.py`, `test_resort_apply_flow.py` (pinned mail is never moved) |
| AC-40 | R1 | Agent `test_list_sync_labels.py`, `test_runner_list_sync.py`; E2E `categories.spec.ts` (rename keeps the id, new name equal to a Gmail label is refused). The label rename in a real Gmail is not tested, see caveats |
| AC-41 | R2 | Agent `test_resort_apply_move_back.py`; E2E `review.spec.ts` (Move back asks the agent exactly once) |
| AC-42 | R2 | Agent `db/test_plan_approval.py`, `db/test_plan_race.py`, `db/test_plan_notice_kinds.py`, `core/test_approval_text.py`, `core/test_resort_plan.py`, `test_approval_notice.py`; E2E `review.spec.ts` (an approval above the threshold waits and Cancel stops it) |
| AC-43 | R2 | Web `ReviewPage.test.tsx`; Api `test_plan_api.py` (progress and not looked at) |
| AC-44 | R2 | Web `features/review/text.test.ts`, `ReviewItems.test.tsx` |
| AC-45 | R2 | No automated test: user acceptance. Manual step: after the first R2 plan is applied, the user checks the 36 first-run mails and the mails flagged on 2026-11-08 and signs off in `docs/release/mail-categories-r2.md` |
| AC-46 | R1 | The report itself: Agent `test_refile_report.py`, `test_runner_refile.py`, `db/test_pg_refile.py` (fake Gmail, real PostgreSQL). The target (under 5 % re-filed, at most 15 % in Other) has no automated test: user acceptance two weeks after R1, signed off in `docs/release/mail-categories-r1.md` |
| AC-47 | R2 | Agent `db/test_plan_approval.py`, `db/test_plan_purge.py` |
| AC-48 | R1, R2 | Agent `test_list_notice_buttons.py`, `test_list_notice_nonce.py`, `test_runner_list_notice.py`, `test_dispatch_plan_buttons.py`, `test_approval_notice.py`, `db/test_pg_list_notice.py`, `db/test_plan_notice_kinds.py` |
| AC-49 | R1 | Agent `test_list_sync_labels.py`; E2E `categories.spec.ts` (not ready before version 1; the stack has no agent, so the test seeds version 1 by SQL) |
| AC-50 | R2 | Agent `core/test_resort_plan.py` |
| AC-51 | R2 | Agent `test_resort_apply_safety.py` (a database failure after the Gmail change ends applied without a second move) with the fault injection of `test_fakes_gmail.py` |
| AC-52 | R2 | Agent `core/test_scope_classify.py`, `test_resort_build_scope.py`, `test_fakes_gmail.py` |
| AC-53 | R1 | Agent `test_list_sync_labels.py`; Web `CategoriesPage.test.tsx`; E2E `categories.spec.ts` (Add to my list) |
| AC-54 | R2 | Agent `test_resort_build_flow.py` |
| AC-55 | R1, R2 | Web `components/ConfirmDialog.test.tsx`, `ReviewPage.test.tsx`; E2E `categories.spec.ts` (keyboard flow of the save summary) |
| AC-56 | R1, R2 | Agent `db/test_categories_purge.py`, `db/test_plan_functions.py` |
| AC-57 | R2 | Agent `test_resort_apply_safety.py` (lock and cancel stop before the next batch), `test_resort_apply_move_back.py`, `core/test_resort_plan.py` |
| AC-58 | R2 | Backend `test_plan_search.py` (filter, sort, stable paging, wildcards, canary, bounds, refusals) |
| AC-59 | R2 | Web `ReviewFilter.test.tsx`, `plan.api.test.ts`; E2E `review.spec.ts` (journey 5b: filter, sort, select the matching mails) |

Criteria with no or only partial automated test:

- AC-45: user acceptance by design (see the row).
- AC-46: the numbers need two weeks of real use; the report is tested, the target is not.
- The real Gmail: every Gmail test runs against the fake of `agents/mail-triage/tests/fakes/fake_gmail.py`, which encodes our assumptions (label rename, search, labels of a message). The manual step is the real-Gmail smoke test of row 7 of `docs/release/mail-categories-r1.md`: read the Categories page, save, receive the Undo notice in Telegram and rename a label.
- AC-24: the time and DOM bounds are not measured; AC-21: the CSP header is not re-tested for the new pages.
- AC-5 to AC-7, AC-25, AC-28 and AC-31 were not run end to end through a browser: the prod-like stack has no agent, no fake Gmail and no fake Telegram (decided in row 4 of the R1 checklist).

## Verification results

Phase 7 ran on a real prod-like stack (db, mail, api, web and the edge over HTTPS):

- Playwright: 81 of 83 tests green (after U-35 and U-36), 2 skipped by design (projects `categories` and `review` included, so `/categories` and `/review` open by link and survive a reload, blocker B-1 of the R1 checklist).
- axe at four widths (320, 375, 768 and 1280 px): no violation; 200 % text: no horizontal scroll.
- Canary strings typed into names, descriptions, senders and subjects are in no log of the stack; headers and logs checks green.
- `Cache-Control: no-store` on list and plan responses holds through the edge; an approve body of 40 KB gets 413.
- Deployment: kubeconform 21 of 21 manifests valid; kube-linter clean.
- `node scripts/check.mjs full`: 38 of 39 checks green at first, the failing one was fixed and the run is green.
- The integration run is green on `main` 31e338f.
- Mutation gate (U-34), score per module: category-policy `policy.py` 100 %, `pinned.py` 92.6 %, `scope.py` 97.4 %, `list_text.py` 99.7 %, `approval_text.py` 95.2 %, `resort_plan.py` 96.7 %. A nightly workflow runs the gate.

## Known caveats

1. The real Gmail smoke test is still to be done by the user. The fake Gmail encodes assumptions; nothing proves them against Google.
2. The IngressRoute for the list save is validated against its schema only (kubeconform); no real Traefik has served it.
3. The web "Cancel" does not exist in R2: a scheduled move is stopped only through the Cancel button of the Telegram message (the review page says so). The web page offers Move back after an apply.
4. `test_settings_store` has a two-session race that is flaky under load.
5. The nightly mutation workflow has not run on GitHub yet; the scores above are the results of the U-34 runs.
6. ADR-0049 (worker egress limited by CIDR) records an accepted residual risk. Before a deploy the production values `networkPolicy.https.podCidr` and `networkPolicy.https.serviceCidr` must be filled in.
7. Not built: a web Cancel (Cancel is Telegram only). The sentence "Saving will create a review of up to N mails" (C-15) was dropped from the spec on 2026-11-17; filter and sort by sender (C-18) was built as U-35 and U-36.
8. The daily report of AC-46 is written to the agent's log and its report table; no Telegram message or web page shows it.
9. In R1 an Undo of a list change does not move back mail filed under it (MR-4, to be accepted by the user in row 8 of the R1 checklist).

## Architecture

The architecture is reconciled on the build branch: `docs/architecture/model.json` gets the component `category-policy` (shared package `packages/category-policy`), `mail-triage` and `api` depend on it, and the responsibilities of `mail-triage`, `api` and `web` are widened (judging against the list, plans and notices; the category and plan API; the pages "Categories" and "Review moves"). The `postgres` component now lists the schema `categories` (list, versions, audit written by the api; label map, plans, plan items with sender and subject for at most 14 days, rejections and apply audit owned by the agent) and the mailbox id on every table. The rendered table in `docs/architecture/README.md` follows. These two files are not on the docs branch yet and arrive with the build branch.

## Approvals

All by the user unless stated otherwise.

| Date | Decision |
| --- | --- |
| 2026-11-14 | Spec approved (D1 to D19); two releases R1 and R2 (D12); the round table decisions D14 to D19. |
| 2026-11-16 | The web lock answers 401 and the sign-in page is the one place that says how to unlock (checklist row 5). |
| Not given | Approval of release R1 for production. |
| Not given | Approval of release R2 for production. |

## Deploy

Not deployed. Phase 9 is not started until the user approves R1 and R2 explicitly. Rollback plan: nothing to roll back yet. The database side comes from the migrations of the agent chain (`0014` onwards, see the units U-03, U-12 and U-26); the application rolls back with the Argo CD release. Locking web sign-in from Telegram (`/web_lock`) refuses every web call to the category and plan API without a redeploy.
