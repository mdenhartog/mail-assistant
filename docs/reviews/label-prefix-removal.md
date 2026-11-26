---
intent: INT-010
spec: docs/specs/label-prefix-removal.md
plan: docs/plans/label-prefix-removal/index.md
pr: https://github.com/mdenhartog/mail-assistant/pull/201
release: not released (unit 15, the contract migration, is built last and ships after the rename is done in production)
---

# Review record: Gmail labels without the Assistant prefix

The feature removes the `Assistant/` prefix from every label the agent manages (INT-010). The category list becomes the boundary of what the agent may touch, the existing labels are renamed once after a preview and a typed confirmation, and the agent deletes an empty label after a waiting time the user sets. The documentation of phase 8 is this record, the [user guide](../user-guide/label-prefix-removal.md), the [API guide](../api/README.md) and the reconciled architecture. Nothing is deployed and nothing is released.

## Gates

| Phase | Result | Evidence |
| --- | --- | --- |
| 1 Spec | Intent INT-010 confirmed; spec revision 3 approved by the user, 2026-11-24 (D1 to D11, P1 to P7, R1 to R10) | `docs/specs/label-prefix-removal.md`, PR #200 |
| 2 Threat model | Written with the round table; T13 to T20 added, A3 accepted by the user under D8 | `docs/security/label-prefix-removal-threat-model.md` |
| 3 Design | ADR-0060 and ADR-0061 accepted | `docs/memory/decisions/` |
| 4 Plan | 21 units; the repairs below are numbered units 22 to 24 | `docs/plans/label-prefix-removal/index.md` |
| 5 Build, test first | Units built on unit branches, each with its failing test first, and landed in the feature branch | `git log` of the feature branch |
| 6 Challenge | Red team and code review ran; the repairs below were landed from their findings | "Challenge and repairs" below |
| 7 Verify | One feature pull request and one CI run. Pull request: #201. CI result: all jobs green after repair rounds r1a to r8a (run on 7b52def). I did not run the prod-like e2e specs locally; CI did | "Known limits" below |
| 8 Finish | Spec `status: done`, user guide, API guide, this record; `node scripts/docs.mjs check` | this record |
| 9 Release | Not started | "Approvals and deploy" below |

## Units

| Unit | What | Component |
| --- | --- | --- |
| U-01 | category-policy v3: names without the prefix, the new name rules and the setting bounds | category-policy |
| U-02 | Migration 0030 (expand): managed labels, rename plan, migration state, timers, settings, deleted-label record | mail-triage |
| U-03 | Managed labels by id, scope without the prefix and filing labels | mail-triage |
| U-04 | Allow-list by managed id and the reflection test | mail-triage |
| U-05 | `list_sync` rebuilt: no seed from Gmail, "Other" and archive by id, the migration gate | mail-triage |
| U-06 | Rename plan runner: build, rename, merge, skip, restore, notice | mail-triage |
| U-07 | Label delete adapter: delete by id with the filter, type and spam and trash checks | mail-triage |
| U-08 | The pure delete rule and the timer store | mail-triage |
| U-09 | Cleanup use case: the cycle, the lease, the daily notice and the deleted-label record | mail-triage |
| U-10 | Api settings: waiting time, protection, retention | api |
| U-11 | Api: rename preview, confirmation, restore, recently deleted | api |
| U-12 | Web: the Label cleanup tile and the Other and archive names | web |
| U-13 | Web: the rename preview, restore, recently deleted and the first-run empty state | web |
| U-14 | End-to-end journey: preview, confirm, merge, wait and delete | web |
| U-15 | Migration 0031 (contract): drop `category_label`, `gmail_label` and `adoptable` | mail-triage; not built, ships later |
| U-16 | category-policy: adopt an existing label, keep the reserved names forbidden | category-policy |
| U-17 | The mail path (triage and catch-up) follows the managed set | mail-triage |
| U-18 | The re-sort path follows the managed set | mail-triage |
| U-19 | Api follows the policy v3 rules | api |
| U-20 | Web follows the policy v3 rules | web |
| U-21 | Database length limits follow the policy (255 characters) | mail-triage |

### Repairs

| Repair | Unit | What |
| --- | --- | --- |
| r1a | U-05 | All label writes are held until the rename is done; the grants of the gate |
| r1b | U-10 | The settings tests of the api; the dead `olderCategories` field removed |
| 02b | U-02 | The web role may insert the first settings row with the label columns (grant) |
| r2a | U-22 | Agent code: the confirmed plan hash is checked again before the rename runs; a 404 on a label delete counts as done; the list is checked again under the lease; shared bounds; the guard chain tested; held extra labels covered |
| r2b | U-23 | Web client: the api schema regenerated without the removed field |
| r3a | U-24 | category-policy: one reserved-names list, the legacy `Assistant/` prefix refused, Unicode tricks covered; threat model T5 now covers the merge |

## Challenge and repairs

The findings of the challenge are recorded in the threat model; the repairs above are their outcome. I did not find a separate numbered finding list in the repository for this feature, so this record does not list one.

| Topic | Decision |
| --- | --- |
| Label writes before the user confirms | Fixed (r1a): a migration state holds every label write until the rename is done (R4, T17) |
| The confirmed plan changed after the preview | Fixed (r2a): the hash is checked again before the rename runs (R5) |
| Delete of a label that is already gone | Fixed (r2a): a 404 counts as done |
| Delete after the list changed | Fixed (r2a): the list is checked again under the lease (R9) |
| Reserved names, the legacy prefix and look-alike names | Fixed (r3a): one reserved list in `category-policy` |
| D8, adopt without a confirmation | Accepted by the user; the protection period of 7 days is the control (A3, T13) |

## Acceptance criteria

The criteria are AC 1 to 34 of the spec. The matrix of criterion and test is in the unit files under `docs/plans/label-prefix-removal/`. This record does not repeat it.

## Known limits

Accepted limits, also described to the user in the user guide:

- **Restore does not undo merges.** A restore gives renamed labels their old names by id; mail that a merge moved onto an existing label stays there.
- **A mail window between the final check and the delete.** Gmail has no conditional delete, so a mail that arrives between the final check and the delete call loses that label. The two calls are adjacent and the outcome is recorded (A2, AC 30).
- **While the migration is pending**, mail that would go under "Other" stays unfiled and is judged again at every poll.
- **Legacy ids of "Other" and the archive label** cannot be copied by the migration, so the hold gate (the migration state) protects the rename.
- **The root label `Assistant`** is deleted by the cleanup once it is empty, like any label outside the list.
- **A hand-made empty label** may be deleted after the waiting time (A1, D6).
- **Not verified here.** The prod-like e2e specs were not run for this record; no screenshots were produced, so the user guide describes the screens in words; the review of the documents for personal names by the user is not done.
- **Unit 15** (the contract migration) is not built.

## Architecture

The design (ADR-0060, ADR-0061) fixed the components; no dependency changed.

- [ADR-0060](../memory/decisions/ADR-0060-list-is-the-label-boundary.md): the list is the label boundary; managed labels by id; delayed delete of empty labels. It supersedes ADR-0059, decision D18 of ADR-0046 and the reserved-segment and label-length parts of ADR-0053 point 3.
- [ADR-0061](../memory/decisions/ADR-0061-one-time-label-rename-plan.md): the one-time rename plan and its agent-api seam: a migration state `pending`, `confirmed`, `done`, an insert-only confirmation through a `SECURITY DEFINER` function, and a backup for a restore by id.
- Migration 0030 (expand) adds the managed labels, rename tables, migration state, timers, settings columns and the deleted-label record; 0031 (contract) is a later release.
- The api gains four label-rename routes and the three label cleanup numbers in the settings route; it still never calls Gmail.

## Approvals and deploy

| Date | Decision |
| --- | --- |
| 2026-11-24 | Spec revision 3 approved by the user; safeguards R1 to R10, the waiting time default of 12 hours and D8 closed |
| Not given | Approval for production |

Deploy: pending (needs the user go-ahead). Pull request: #201. CI: green on 7b52def.
