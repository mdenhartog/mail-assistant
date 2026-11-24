---
intent: INT-010
feature: label-prefix-removal
spec: docs/specs/label-prefix-removal.md
---

# Gmail labels without the Assistant prefix

The plan for `docs/specs/label-prefix-removal.md` (revision 3, approved), ADR-0060, ADR-0061 and the threat model `docs/security/label-prefix-removal-threat-model.md`. Eighteen units: seventeen in one release and one contract migration that ships after the rename is `done` in production.

## Units

| Unit | Name | Layer | Depends on | Parallel | Wave |
|---|---|---|---|---|---|
| [U-label-prefix-removal-01](U-label-prefix-removal-01.md) | category-policy v3: names without the prefix, the new name rules and the setting bounds | backend | — | yes | 1 |
| [U-label-prefix-removal-02](U-label-prefix-removal-02.md) | Migration 0030 (expand): managed labels, rename plan, migration state, timers, settings and the deleted-label record | backend | U-label-prefix-removal-01 | yes | 2 |
| [U-label-prefix-removal-03](U-label-prefix-removal-03.md) | Agent core: managed labels by id, scope without the prefix and filing labels | backend | U-label-prefix-removal-01 | yes | 2 |
| [U-label-prefix-removal-16](U-label-prefix-removal-16.md) | category-policy: adopt an existing label and allow the names Other and Archive in the list | backend | U-label-prefix-removal-01 | yes | 2 |
| [U-label-prefix-removal-04](U-label-prefix-removal-04.md) | Agent adapters: allow-list by managed id and the reflection test | backend | U-label-prefix-removal-03 | yes | 3 |
| [U-label-prefix-removal-08](U-label-prefix-removal-08.md) | Cleanup decision: the pure delete rule and the timer store | backend | U-label-prefix-removal-02, U-label-prefix-removal-03 | yes | 3 |
| [U-label-prefix-removal-10](U-label-prefix-removal-10.md) | Api: settings for the waiting time, protection, retention and the names of Other and archive | backend | U-label-prefix-removal-01, U-label-prefix-removal-02 | yes | 3 |
| [U-label-prefix-removal-05](U-label-prefix-removal-05.md) | list_sync rebuilt: no seed from Gmail, "Other" and archive by id, the migration gate | backend | U-label-prefix-removal-02, U-label-prefix-removal-03, U-label-prefix-removal-04 | no | 4 |
| [U-label-prefix-removal-07](U-label-prefix-removal-07.md) | Gmail label delete adapter: delete by id with the filter, type and spam/trash checks | backend | U-label-prefix-removal-04 | yes | 4 |
| [U-label-prefix-removal-11](U-label-prefix-removal-11.md) | Api: the rename preview, the confirmation, the restore and the recently deleted record | backend | U-label-prefix-removal-02, U-label-prefix-removal-10 | yes | 4 |
| [U-label-prefix-removal-17](U-label-prefix-removal-17.md) | Agent mail path follows the managed set: triage and catch-up | backend | U-label-prefix-removal-03, U-label-prefix-removal-04 | yes | 4 |
| [U-label-prefix-removal-18](U-label-prefix-removal-18.md) | Agent re-sort path follows the managed set: build, apply, move back, report | backend | U-label-prefix-removal-03, U-label-prefix-removal-04 | yes | 4 |
| [U-label-prefix-removal-06](U-label-prefix-removal-06.md) | Rename plan runner: build, rename, merge, skip, restore, notice | backend | U-label-prefix-removal-05 | yes | 5 |
| [U-label-prefix-removal-09](U-label-prefix-removal-09.md) | Cleanup use case: the cycle, the lease, the daily notice and the deleted-label record | backend | U-label-prefix-removal-05, U-label-prefix-removal-07, U-label-prefix-removal-08 | no | 5 |
| [U-label-prefix-removal-12](U-label-prefix-removal-12.md) | Web: the Label cleanup tile on the Settings page and the two names on the Categories page | web | U-label-prefix-removal-10 | yes | 5 |
| [U-label-prefix-removal-13](U-label-prefix-removal-13.md) | Web: the rename preview, restore, recently deleted and the first-run empty state | web | U-label-prefix-removal-11 | yes | 6 |
| [U-label-prefix-removal-14](U-label-prefix-removal-14.md) | End-to-end journey: preview, confirm, merge, wait and delete | web | U-label-prefix-removal-06, U-label-prefix-removal-09, U-label-prefix-removal-12, U-label-prefix-removal-13 | no | 7 |
| [U-label-prefix-removal-15](U-label-prefix-removal-15.md) | Migration 0031 (contract): drop category_label, gmail_label and adoptable | backend | U-label-prefix-removal-14 | no | 8 |

## Build order

1. Wave 1 — one unit: U-label-prefix-removal-01
2. Wave 2 — three units, at most two build agents at a time: U-label-prefix-removal-02, U-label-prefix-removal-03, U-label-prefix-removal-16
3. Wave 3 — three units, at most two build agents at a time: U-label-prefix-removal-04, U-label-prefix-removal-08, U-label-prefix-removal-10
4. Wave 4 — five units, at most two build agents at a time: U-label-prefix-removal-05, U-label-prefix-removal-07, U-label-prefix-removal-11, U-label-prefix-removal-17, U-label-prefix-removal-18
5. Wave 5 — three units, at most two build agents at a time: U-label-prefix-removal-06, U-label-prefix-removal-09, U-label-prefix-removal-12
6. Wave 6 — one unit: U-label-prefix-removal-13
7. Wave 7 — one unit: U-label-prefix-removal-14
8. Wave 8 — one unit, a later release: U-label-prefix-removal-15

Unit 15 is built last and released only after the one-off rename has run on the real mailbox.

## Placement

| Responsibility | Component | Why here | Alternatives rejected | ADR |
|---|---|---|---|---|
| Label naming, the names of "Other" and archive, the setting bounds | `category-policy` | one rule set for agent and api | duplicate rules in both | ADR-0060 |
| Managed label ids, rename tables, timers, deleted-label record, settings columns | `mail-triage agent` (migration chain) | the agent owns the Gmail state and the schema `categories` | a table owned by the api | ADR-0060, ADR-0061 |
| Scope and the allow-list by managed id | `mail-triage agent` core and adapters | the agent owns the Gmail boundary | the api deciding scope | ADR-0060 |
| The delete rule, the timer and the daily notice | `mail-triage agent` | long-running cycle that owns the Gmail credentials | the api (no Gmail access, ADR-0011) | ADR-0060 |
| The rename plan runner and the merge | `mail-triage agent` | the only component that writes labels and mail labels | the api calling Gmail | ADR-0061 |
| The confirmation, the preview, the restore and the settings routes | `api` | the user's session and CSRF live here | the agent reading the web | ADR-0061 |
| The Label cleanup tile, the two name fields, the preview page and the recently deleted list | `web` | user interface only | business rules in the browser | ADR-0061 |
