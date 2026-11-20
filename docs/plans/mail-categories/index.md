---
intent: INT-004
feature: mail-categories
spec: docs/specs/mail-categories.md
---

# Mail categories

Units U-01 to U-11 are release R1 (list, Categories page, judging, Archive label, notices); U-12 to U-19 are release R2 (plans, review, apply, Move back). A wave starts when the previous one is merged.

## Units

| Unit | Name | Layer | Depends on | Parallel | Wave |
|---|---|---|---|---|---|
| [U-mail-categories-01](U-mail-categories-01.md) | Test fakes and seed data | backend | — | yes | 1 |
| [U-mail-categories-02](U-mail-categories-02.md) | category-policy package | backend | — | yes | 1 |
| [U-mail-categories-03](U-mail-categories-03.md) | Categories schema, roles and list-side functions | backend | U-mail-categories-01, U-mail-categories-02 | no | 2 |
| [U-mail-categories-04](U-mail-categories-04.md) | List API | backend | U-mail-categories-02, U-mail-categories-03 | yes | 3 |
| [U-mail-categories-05](U-mail-categories-05.md) | Judging against the list | backend | U-mail-categories-01, U-mail-categories-02, U-mail-categories-03 | no | 3 |
| [U-mail-categories-06](U-mail-categories-06.md) | Label sync and the Archive label | backend | U-mail-categories-01, U-mail-categories-03, U-mail-categories-05 | no | 4 |
| [U-mail-categories-07](U-mail-categories-07.md) | List notice, Undo and Telegram actions | backend | U-mail-categories-06 | no | 5 |
| [U-mail-categories-08](U-mail-categories-08.md) | Web foundations: dialog tone, navigation, card | web | — | yes | 1 |
| [U-mail-categories-09](U-mail-categories-09.md) | Categories page | web | U-mail-categories-04, U-mail-categories-08 | no | 4 |
| [U-mail-categories-10](U-mail-categories-10.md) | AC-46 daily report | backend | U-mail-categories-05, U-mail-categories-06 | yes | 5 |
| [U-mail-categories-11](U-mail-categories-11.md) | R1 end-to-end | web | U-mail-categories-07, U-mail-categories-09, U-mail-categories-10, U-mail-categories-20, U-mail-categories-21, U-mail-categories-23, U-mail-categories-25 | no | 8 |
| [U-mail-categories-12](U-mail-categories-12.md) | Plan schema and decision functions | backend | U-mail-categories-03 | yes | 3 |
| [U-mail-categories-13](U-mail-categories-13.md) | Plan state machine | backend | U-mail-categories-02 | yes | 2 |
| [U-mail-categories-14](U-mail-categories-14.md) | Plan build | backend | U-mail-categories-05, U-mail-categories-12, U-mail-categories-13 | no | 4 |
| [U-mail-categories-15](U-mail-categories-15.md) | Plan apply and Move back | backend | U-mail-categories-06, U-mail-categories-14 | no | 5 |
| [U-mail-categories-16](U-mail-categories-16.md) | Approvals, Cancel and Lock in Telegram | backend | U-mail-categories-07, U-mail-categories-15 | no | 6 |
| [U-mail-categories-17](U-mail-categories-17.md) | Plan, approve and move-back API | backend | U-mail-categories-12 | yes | 4 |
| [U-mail-categories-18](U-mail-categories-18.md) | Review moves page | web | U-mail-categories-08, U-mail-categories-17 | no | 5 |
| [U-mail-categories-19](U-mail-categories-19.md) | R2 end-to-end | web | U-mail-categories-16, U-mail-categories-18, U-mail-categories-22, U-mail-categories-24 | no | 7 |
| [U-mail-categories-20](U-mail-categories-20.md) | Ingress route for the list save | infra | U-mail-categories-04 | yes | 4 |
| [U-mail-categories-21](U-mail-categories-21.md) | Run the list sync in the agent | backend | U-mail-categories-05, U-mail-categories-06 | yes | 5 |
| [U-mail-categories-22](U-mail-categories-22.md) | Connect plan build and apply to PostgreSQL and Gmail | backend | U-mail-categories-14, U-mail-categories-15, U-mail-categories-21 | no | 6 |
| [U-mail-categories-23](U-mail-categories-23.md) | Connect the list notice and Telegram actions to PostgreSQL | backend | U-mail-categories-07, U-mail-categories-21 | no | 6 |
| [U-mail-categories-24](U-mail-categories-24.md) | Plan progress, group approvals and the open-items badge | backend | U-mail-categories-17, U-mail-categories-18 | yes | 6 |
| [U-mail-categories-25](U-mail-categories-25.md) | Connect the daily re-file report to PostgreSQL and Gmail | backend | U-mail-categories-10, U-mail-categories-23 | no | 7 |
| [U-mail-categories-26](U-mail-categories-26.md) | Plan apply timing and the scheduling guard | backend | U-mail-categories-22, U-mail-categories-23 | no | 9 |
| [U-mail-categories-27](U-mail-categories-27.md) | Review fixes: archive label, names, authentication results, log redaction | backend | U-mail-categories-05, U-mail-categories-06 | no | 9 |
| [U-mail-categories-28](U-mail-categories-28.md) | Review fixes: hidden SQL parameters, debounce, retries, notice wording | backend | U-mail-categories-22 | no | 9 |
| [U-mail-categories-29](U-mail-categories-29.md) | Review page wording and status | web | U-mail-categories-18 | no | 9 |
| [U-mail-categories-30](U-mail-categories-30.md) | Categories page leave guard and save bar | web | U-mail-categories-09 | no | 9 |
| [U-mail-categories-31](U-mail-categories-31.md) | Worker HTTPS egress limited by CIDR | infra | U-mail-categories-22 | no | 9 |
| [U-mail-categories-32](U-mail-categories-32.md) | Plan view: example, apply settings, moved count | backend | U-mail-categories-17, U-mail-categories-24 | no | 9 |
| [U-mail-categories-33](U-mail-categories-33.md) | Last plan | backend | U-mail-categories-32 | no | 9 |
| [U-mail-categories-34](U-mail-categories-34.md) | Mutation gate for the INT-004 pure modules | backend | U-mail-categories-02, U-mail-categories-05 | no | 9 |
| [U-mail-categories-35](U-mail-categories-35.md) | Filter and sort the plan items by sender | backend | U-mail-categories-32 | no | 10 |
| [U-mail-categories-36](U-mail-categories-36.md) | Filter and sort controls on the Review moves page | web | U-mail-categories-35 | no | 10 |
| [U-mail-categories-37](U-mail-categories-37.md) | A failed step names the Gmail status and reason in the log | backend | U-mail-categories-21 | yes | 11 |
| [U-mail-categories-38](U-mail-categories-38.md) | A label name that Gmail refuses does not stop the label sync | backend | U-mail-categories-37 | no | 12 |

## Build order

1. Wave 1 (units with Parallel yes run together, each in its own worktree): U-mail-categories-01, U-mail-categories-02, U-mail-categories-08
2. Wave 2 (units with Parallel yes run together, each in its own worktree): U-mail-categories-03, U-mail-categories-13
3. Wave 3 (units with Parallel yes run together, each in its own worktree): U-mail-categories-04, U-mail-categories-05, U-mail-categories-12
4. Wave 4 (units with Parallel yes run together, each in its own worktree): U-mail-categories-06, U-mail-categories-09, U-mail-categories-14, U-mail-categories-17, U-mail-categories-20
5. Wave 5 (units with Parallel yes run together, each in its own worktree): U-mail-categories-07, U-mail-categories-10, U-mail-categories-15, U-mail-categories-18, U-mail-categories-21
6. Wave 6 (units with Parallel yes run together, each in its own worktree): U-mail-categories-16, U-mail-categories-22, U-mail-categories-23, U-mail-categories-24
7. Wave 7 (units with Parallel yes run together, each in its own worktree): U-mail-categories-19, U-mail-categories-25

## Placement

| Responsibility | Component | Units |
|---|---|---|
| Name and list rules | category-policy | U-02 |
| Schema, grants, functions, retention | mail-triage (migration chain) | U-03, U-12 |
| Judging, pinned mail, filing | mail-triage | U-05 |
| Label sync, Archive, rename, counts | mail-triage | U-06 |
| List notice, Undo, Telegram actions | mail-triage | U-07, U-16 |
| Plan state machine, build, apply, Move back | mail-triage | U-13, U-14, U-15 |
| List API, plan and approval API | api | U-04, U-17 |
| Pages, dialog tone, navigation | web | U-08, U-09, U-18 |
| Test fakes | mail-triage (tests) | U-01 |
| End-to-end | web (e2e) | U-11, U-19 |

## Test pyramid

Unit (policy, state machine, classifier, parsers, formatters), integration on real PostgreSQL (migrations, privilege matrix, functions, races, retention), contract (OpenAPI with schemathesis, `category_cases.json`, fake versus real Gmail), component (Vitest, Testing Library, axe), end-to-end (Playwright) and a canary scan. Every criterion has a test named `test_<unit>_<behaviour>`; the AC ids of the spec are in the criteria.
8. Wave 8 (units with Parallel yes run together, each in its own worktree): U-mail-categories-11
9. Wave 9 (review and verify fixes, one at a time): U-mail-categories-26, U-mail-categories-27, U-mail-categories-28, U-mail-categories-29, U-mail-categories-30, U-mail-categories-31, U-mail-categories-32, U-mail-categories-33, U-mail-categories-34
10. Wave 10 (sender filter and sort, one at a time): U-mail-categories-35, U-mail-categories-36
11. Wave 11 (operations fix after the first deploy, in parallel): U-mail-categories-37
12. Wave 12 (operations fix after the first deploy, one at a time): U-mail-categories-38
