---
intent: INT-011
feature: daily-budget-partial-plan
spec: docs/specs/daily-budget-partial-plan.md
---

# A higher daily model budget and a plan in parts

The plan for `docs/specs/daily-budget-partial-plan.md` (revision 2, approved), ADR-0062, ADR-0063 and the threat model `docs/security/daily-budget-partial-plan-stride.md`. Thirteen units. The budget gets stored and paced (U-01, U-02, U-04, U-05); the plan gets parts, a watermark cursor, series rules, one notice a day and a plan view (U-03, U-06 to U-12); one end-to-end journey closes it (U-13). Raising the number on the user's own stack is a deploy and needs the user's go-ahead.

## Units

| Unit | Name | Layer | Depends on | Parallel | Wave |
|---|---|---|---|---|---|
| [U-daily-budget-partial-plan-01](U-daily-budget-partial-plan-01.md) | The daily budget setting: 500 by default and a bound | backend | — | yes | 1 |
| [U-daily-budget-partial-plan-02](U-daily-budget-partial-plan-02.md) | Migration (expand): the model-budget ledger and its spend function | backend | — | yes | 1 |
| [U-daily-budget-partial-plan-04](U-daily-budget-partial-plan-04.md) | The pacing rule (pure) | backend | — | yes | 1 |
| [U-daily-budget-partial-plan-06](U-daily-budget-partial-plan-06.md) | The series rules (pure) | backend | — | yes | 1 |
| [U-daily-budget-partial-plan-07](U-daily-budget-partial-plan-07.md) | The watermark cursor and the poison mail | backend | — | yes | 1 |
| [U-daily-budget-partial-plan-03](U-daily-budget-partial-plan-03.md) | Migration (expand): plan parts, series columns, the notice record and column grants | backend | U-daily-budget-partial-plan-02 | no | 2 |
| [U-daily-budget-partial-plan-05](U-daily-budget-partial-plan-05.md) | The stored budget replaces the in-memory counter | backend | U-daily-budget-partial-plan-02, U-daily-budget-partial-plan-04 | no | 2 |
| [U-daily-budget-partial-plan-08](U-daily-budget-partial-plan-08.md) | The plan store: parts, the lease and the series end | backend | U-daily-budget-partial-plan-03, U-daily-budget-partial-plan-06 | no | 3 |
| [U-daily-budget-partial-plan-11](U-daily-budget-partial-plan-11.md) | Api: the plan view with part and pause reason, and the 409 | backend | U-daily-budget-partial-plan-03 | yes | 3 |
| [U-daily-budget-partial-plan-09](U-daily-budget-partial-plan-09.md) | Build in parts | backend | U-daily-budget-partial-plan-01, U-daily-budget-partial-plan-05, U-daily-budget-partial-plan-06, U-daily-budget-partial-plan-07, U-daily-budget-partial-plan-08 | no | 4 |
| [U-daily-budget-partial-plan-10](U-daily-budget-partial-plan-10.md) | The one daily notice and the announced gate | backend | U-daily-budget-partial-plan-08 | yes | 4 |
| [U-daily-budget-partial-plan-12](U-daily-budget-partial-plan-12.md) | Web: "Review moves" shows the part and why a plan waits | web | U-daily-budget-partial-plan-11 | yes | 4 |
| [U-daily-budget-partial-plan-13](U-daily-budget-partial-plan-13.md) | End-to-end: the journey of a paused part | web | U-daily-budget-partial-plan-12 | no | 5 |

## Build order

1. Wave 1 — in parallel (at most two build agents at a time): U-01, U-02, U-04, U-06, U-07
2. Wave 2 (after wave 1) — one at a time because both touch the migration chain or the budget: U-03, U-05
3. Wave 3 — U-08 and U-11 in parallel
4. Wave 4 — U-09 on its own (it rebuilds the build use case); U-10 and U-12 in parallel with each other
5. Wave 5 — U-13

The migration of U-03 must come after U-02 in the Alembic chain; the revision number after 0030 is taken at build time (0031 stays reserved for the INT-010 contract migration).

## Placement

| Responsibility | Component | Why here | Alternatives rejected | ADR |
|---|---|---|---|---|
| The model budget count, its spend function and the pace rule | `mail-triage` agent (with a ledger in `postgres`) | The agent spends the calls; the database is the one place two instances share | Redis (a new component), the api (it never calls the model) | ADR-0062 |
| Plan parts, the series rules, the cursor and the notice | `mail-triage` agent | The build and the apply flow already live here | A new worker (no new lifecycle) | ADR-0063 |
| The plan view and the 409 | `api` | The web reads and writes through it; the agent never serves the web | The web reading the table (it has only a column-level grant) | ADR-0063 |
| The paused and part states | `web` | "Review moves" is a web screen | — | ADR-0063 |

## Coverage of the acceptance criteria

| Criteria | Units |
|---|---|
| AC 1, SAC-18 | U-01, U-05 |
| AC 2, 3 | U-08, U-09 |
| AC 4, 5, 6, 7 | U-06, U-08, U-09 |
| AC 8, 13, 21, SAC-1, 2, 8 | U-02, U-05 |
| AC 9, 22, SAC-5, 6, 7 | U-04, U-05, U-09 |
| AC 10, 20, SAC-14, 15 | U-10 |
| AC 11, 12, 23, SAC-16 | U-03, U-11, U-12, U-13 |
| AC 14, SAC-17 | U-05, U-07, U-08, U-09, U-10 |
| AC 15, 16, 17, 18, 19, SAC-3, 4, 9, 10, 11, 12, 13 | U-03, U-06, U-07, U-08, U-11, U-13 |
