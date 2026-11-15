---
feature: mail-categories
intent: INT-004
spec: docs/specs/mail-categories.md
unit: U-mail-categories-11
release: R1
status: open
date: 2026-11-15
---

# Release checklist: mail categories, R1 (the list and the page "Categories")

R1 is built on the integration branch but not released. This page says what the end-to-end run of U-mail-categories-11 showed, what it could not show, what blocks the release and what the user signs off. Phase 9 (release) is never started without the user's explicit approval; the last row of the checklist is that approval.

## What ran, and where

The prod-like stack has `db`, `mail`, `api`, `web` and `edge`. It has no agent, no fake Gmail and no fake Telegram, and it cannot get them without a change of production code: the agent calls the fixed addresses `https://oauth2.googleapis.com/token` and `https://api.telegram.org` and builds its Gmail client with `googleapiclient.discovery.build("gmail", "v1")` (`agents/mail-triage/app/wiring.py`, `app/adapters/telegram_inbox.py`). A fake Gmail container would need a setting for the Gmail, token and Telegram addresses first. So the journeys are split in two halves that meet at the database (the stored list, its versions and its audit record).

| Half | Where | What it proves |
| --- | --- | --- |
| The page, the api and the database | `apps/web/e2e/categories.spec.ts`, project `categories`, over the prod-like stack (real browser, HTTPS edge, TLS database) | The user edits, saves and sees the result; what is stored |
| The agent with a fake Gmail and a fake Telegram on a real PostgreSQL | `agents/mail-triage/tests` (run by the agent's pytest, not by Playwright) | New mail follows the list, rename by id, Undo, notice, Archive label, daily report |
| Every state of the page at four widths, light and dark, 200 % text | `apps/web/e2e/ui-states.spec.ts` (stubbed api, no Docker) | axe, overflow, target size |

### Journeys against the acceptance criteria

Run of 2026-11-15 on Windows 11 with Docker Desktop (compose project `ma-e2e11`, loopback ports 15432, 18025, 18080, 18081 and 18443, so the stack the user runs for their own work was not touched). `E2E_IGNORE_HTTPS_ERRORS=1` was set, because the browser of this machine does not trust the private CA; CI does not set it.

| AC | Journey | Result |
| --- | --- | --- |
| AC-1 | The page shows the list with name, description and number of mails, and "Other" | Ran, green (`categories.spec.ts`, test 3) |
| AC-2 | Edit and save: summary, version 2 stored whole by the web channel, audit record, no review; ten refused values, each with its reason and nothing stored; save without a change makes no version | Ran, green (tests 4, 5, 6, 6b) |
| AC-3 | A list changed elsewhere gives a conflict and the page shows the newest list | Ran, green (test 7) |
| AC-22 | A visitor is sent to sign-in; `GET` and `PUT /api/categories` without a session are refused | Ran, green (test 1) |
| AC-23 | Real stack: loaded, validation error, save summary, saved, conflict and not ready at 320, 375, 768 and 1280 px, and at 200 % text; keyboard flow. Stubbed: all 143 categories and review states | Ran, green (tests 11, 13 and `ui-states`) |
| AC-30 | Canary strings typed into names and descriptions are in no log of edge, web, api, db or mail (the logs are shown to hold the requests) | Ran, green (test 14) |
| AC-32 | A locked web refuses the list calls, the page falls back to sign-in and nothing is stored | Ran, green (test 12); see open point 3 |
| AC-40 | A rename keeps the category id, makes no plan and the summary says only the label name changes; a new name equal to an existing Gmail label is refused | Ran, green (tests 8 and 6b). The label rename in Gmail did not run end to end, see below |
| AC-49 | Before version 1 the page says the categories are not ready | Ran, green (test 2) |
| AC-53 | "Add to my list" adds the older category | Ran, green (test 9) |
| AC-31 | The Telegram notice with old and new list and Undo | Not run in the browser (no Telegram in the stack). The agent's own tests ran against PostgreSQL with a fake Telegram: 70 tests of `test_list_notice_flow`, `test_list_notice_buttons`, `test_runner_list_notice`, `test_pg_list_notice`, `test_list_sync_labels`, `test_runner_list_sync`, `test_list_sync_pg` and `test_refile_report`, all passed on 2026-11-15 |
| AC-5, AC-6, AC-7, AC-38, AC-39 | New mail follows the list; hostile model output goes to "Other"; urgent and security mail | Not run end to end (no model and no Gmail in the stack); covered by the agent's pytest only |
| AC-25, AC-28 | `Archive` label and the Gmail allow-list | Not run end to end; covered by the agent's pytest only |
| (journey) | Old mail untouched after a save | Web half only: a save makes no plan and writes only the list. The Gmail half (no mail is moved by a list change) is not shown end to end |

The journeys cover behaviour that already existed, so they are regression guards: none of them was red because a feature was missing. The first runs were red for two reasons that are now fixed in the test (a wrong assumption about adopting an older label, and an axe reading taken during the banner's fade-in) and for one real defect (blocker 1).

## Blockers found by the run

| # | Finding | Effect | Owner of the fix |
| --- | --- | --- | --- |
| B-1 (fixed in the code, e2e re-run pending) | `apps/web/nginx.conf` serves the app only for `/`, `/login` and `/settings` and answers 404 for everything else (AC-19 of web-settings), so `/categories` and `/review` return 404 when opened by link, reload or bookmark. Navigation inside the app works. | The page can only be reached through the navigation after signing in. Test 0 of `categories.spec.ts` documents it with `test.fail`; it turns red when the route is added, which is the cue to remove `test.fail`. The test of the nginx config that asserts exactly three routes must change with it. | A fix unit for `apps/web` (not part of U-11) |
| B-2 | `backend/Dockerfile.dockerignore` does not allow `packages/category-policy`, so `docker compose build api` fails with "`/packages/category-policy/pyproject.toml`: not found". The api image cannot be built from the integration branch, so neither can the prod-like stack or the CI job `prod-like`. | The run used a copy of the file with the two missing allow lines (`!packages/category-policy/pyproject.toml`, `!packages/category-policy/category_policy`) kept outside the repository. | A fix for `backend/` (not part of U-11) |

## Open points

1. **No fake Gmail or Telegram in the stack** (above). To run AC-31 and AC-40 in a browser journey, a unit must first make the agent's Google token address, Gmail address and Telegram address settings, with a fake service for each in `deploy/prod-like/`. The fake Gmail of `agents/mail-triage/tests/fakes/fake_gmail.py` is an in-process Python object and cannot be reached over HTTP.
2. `tests/infra/test_env_example.py` fails on the integration branch for eleven compose variables; the user adds them to `.env.example`.
3. AC-32 asks that the page "says how to unlock". The built behaviour does not: a locked web answers 401 and the page returns to sign-in, because the lock must leave no trace (RT3-03 of web-settings). The unlock is `/web_unlock` in Telegram. Decide whether the spec or the page changes.
4. The e2e `categories` project seeds version 1 by owner SQL because the stack has no agent (AC-49 says the agent seeds it).
5. A local run on a machine whose browser does not trust the private CA must trust the private CA first (the Playwright config keeps certificate checks on); it also needs `E2E_BASE_URL`, `MAIL_URL` and `COMPOSE_PROJECT_NAME` set for the stack under test. The helpers `support/db.ts` and `support/categoriesDb.ts` run SQL in the compose project named by `COMPOSE_PROJECT_NAME`; without it they use the default project, which is the user's own stack.

## Checklist

| # | Item | Owner | Evidence needed | Status |
| --- | --- | --- | --- | --- |
| 1 | B-1 fixed: `/categories` and `/review` open by link and survive a reload. | Build | Test 0 of `categories.spec.ts` without `test.fail`, green. | Code fixed; re-run of the e2e pending |
| 2 | B-2 fixed: the api image builds from a clean checkout. | Build | `docker compose --profile prod-like build api` succeeds. | Open |
| 3 | The CI job `prod-like` runs the `categories` project green (it needs B-2). | Build | The job log. | Open |
| 4 | An end-to-end run with the agent, a fake Gmail and a fake Telegram (open point 1) for AC-31 and AC-40. | Build | The journeys listed under "Not run". | Open (not built) |
| 5 | Open point 3 decided: how the page treats the web lock. | The user | A decision in the spec or an ADR. | Open |
| 6 | Gmail OAuth consent screen is "In production", so the refresh token does not expire after 7 days (row 15 of `web-settings-prod.md`). | The user | The status with its date. | Open |
| 7 | The user has read the Categories page on the local stack with the real Gmail: list, save summary, Undo notice in Telegram, rename of a label in Gmail. | The user | A dated note: what worked and what did not. | Open |
| 8 | MR-4 accepted: in R1 an Undo restores the list but does not move back mail already filed under it (AC-41 comes with R2). | The user | A dated note that the risk is accepted. | Open |
| 9 | **User acceptance with data (AC-46, D19).** Two weeks after R1 is released, fewer than 5 % of new mails were re-filed by hand and at most 15 % of new mail is under "Other". The numbers come from the agent's daily re-file report (the label recorded in its `filing` rows against the mail's current label, divided by the mails filed in the period). | The user | The report values for the two weeks (percent re-filed by hand, percent under "Other", number of mails in the period, the cap of the report), the date range, and the user's words that they accept or do not accept. | Open (starts at release) |
| 10 | The user approves R1 for production explicitly. Phase 9 is not started before this. | The user | Their written approval in the pull request or the review record, with the date. | Not given |

## Sign-off of AC-46

To be filled in by the user two weeks after the release.

| Field | Value |
| --- | --- |
| Release date | |
| Period (from, to) | |
| Mails filed in the period | |
| Re-filed by hand (percent; target under 5 %) | |
| Under "Other" (percent; target at most 15 %) | |
| Mails the report could not check (cap) | |
| Accepted by the user (yes or no, date) | |
