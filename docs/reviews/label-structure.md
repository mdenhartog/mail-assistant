---
intent: INT-008
spec: docs/specs/label-structure.md
plan: docs/plans/label-structure/index.md
pr: R1 is built in the pull requests listed under "Units and pull requests"; R2 is one feature pull request, to be filled when opened
release: not released (R1 and R2 are built; R2 is in the second part of this file)
---

# Review record: label structure, sender rules and always-notify (release R1)

The feature lets the user describe their own label structure: nested categories, topics and extra labels, sender lists that file mail without the model choosing the category, a tick per category that sends an alert for every new mail, and a YAML file to upload, restore and export the list. It is planned in 38 units and two releases (the index is `docs/plans/label-structure/index.md`). This record covers release R1: units 01 to 17 and 28 to 38. Release R2 (units 18 to 27 and 39: archive label name, "Sort everything again" with the confidence threshold, system approval and tips) is recorded in the second part of this file. Nothing is deployed and nothing is released. The documentation of phase 8 is this record, the [user guide](../user-guide/label-structure.md) and the [API guide](../api/README.md).

## Gates

| Phase | Result | Evidence |
| --- | --- | --- |
| 1 Spec | Intent INT-008 confirmed; spec revision 2 approved by the user, 2026-11-21 | `docs/specs/label-structure.md`, PRs #158 and #159 |
| 2 Threat model | Written, with the round table; AR-1 to AR-3 accepted by the user; amended after the R1 challenge | `docs/security/label-structure-threat-model.md`, `docs/reviews/label-structure-roundtable.md` |
| 3 Design | Approved; ADR-0053 to ADR-0059 accepted | `docs/design/label-structure-design.md`, PR #160 |
| 4 Plan | 38 units in two releases; units 28 to 38 were added during the build (see the plan index) | `docs/plans/label-structure/index.md` |
| 5 Build, test first | R1 units built on unit branches and landed by pull request (list below) | `git log` of `main` |
| 6 Challenge | Red team, code review and dependency audit ran on the R1 code; fixes in #194, #195 and #196 | "Challenge" below |
| 7 Verify | CI green on every merged R1 pull request (checks `SUCCESS`, optional jobs skipped). I did not run the prod-like e2e specs for this record (no Docker); whether each pull request ran them depends on the CI scope rules | "Known limits" below |
| 8 Finish | Spec `status: done` for R1, user guide, API guide, threat model and architecture reconciled, this record | `node scripts/docs.mjs check`, `node scripts/architecture.mjs check` |
| 9 Release | Not started | "Deploy" below |

## Units and pull requests

| Pull request | Units | What |
| --- | --- | --- |
| #164 | U-01 | Agent test fakes for headers, a scripted model and a kill point |
| #166 | U-06 | The automatic plan after a list change and at first start is removed |
| #168 | U-07 | One authenticated-sender verifier for pinned mail and sender rules |
| #169 | U-02, U-28, U-29, U-30, U-31 | Category contract v2 (names per segment, kinds, limits) in the shared package and its consumers |
| #170 | U-03 | Sender entry rules, the pure matcher, the refused domains |
| #171 | U-05 | Migration 0024, contract v2, additive |
| #173 | U-04 | The YAML category file, its limits and the template |
| #177 | U-11, U-33, U-34 | The category list v2 in the api and the web body, the ingress limit of the list save |
| #178 | U-32 | The filing code on topic and source, migration 0025 |
| #180 | U-15 | The Categories page as a nested list with an edit view |
| #181 | U-08 | Sender-rule filing without a category call |
| #182 | U-12, U-35 | Upload with a bound preview, confirm, restore, the ingress limit of the upload route |
| #183 | U-13 | Export and the template and example files |
| #184 | U-09 | Judging with topic and extra label, the urgency-only call |
| #185 | U-10 | One alert with every cause and the always-notify text, migration 0026 |
| #187 | U-16 | Web: upload, preview, confirm, restore and export |
| #188 | U-36 | Skipped sender rules recorded per entry, migration 0027 |
| #189 | U-37 | The skipped count of every sender entry in the api |
| #190 | U-14 | The list audit content, the success numbers, migration 0028 |
| #191 | U-38 | The skipped count beside a sender entry on the page |
| #193 | U-17 | The R1 journey with axe, zoom and keyboard |
| #194, #195, #196 | challenge fixes | See "Challenge" |

Plan-only pull requests: #163, #165, #167, #172, #174, #176, #179 and #186. Pull requests #157, #161, #162 and #175 were small fixes found on the way (host name lookup, test roles, pyright, Python pin); they are not units.

## Challenge

The red-team round (RED), the code review (REV) and the dependency audit ran on the R1 code. The dependency audit was clean. The outcome per finding, also recorded in the threat model:

| Finding | What | Decision |
| --- | --- | --- |
| RED-001 | A look-alike domain could match a sender entry (Unicode case folding) | Fixed in #195: comparison as A-labels |
| RED-002 | A model reason in a sender-rule alert could become a link | Fixed in #195: the reason is shown in a code span and a reason that could become a link is refused |
| RED-003 | Several `From` headers were read as a sender | Fixed in #195: no sender, the mail goes to the model |
| RED-005 | The browser re-decoded the file before upload, hiding a byte order mark or an encoding problem | Fixed in #196: the bytes are sent unchanged |
| RED-006 | A session could store thousands of previews within the purge window | Fixed in #194: previews per session are limited per hour |
| RED-007 | The YAML parse blocked the event loop | Fixed in #194: the parse runs off the event loop |
| RED-004 | `archiveLabel` in a file is validated and ignored until R2 | Accepted for R1 and documented; decision pending for the owner (keep it stored or refuse the field until R2) |
| RED-008 | A forged topmost `Authentication-Results` header for mail that did not enter through Google's MX | Accepted risk next to AR-3 unless a decision says otherwise |
| REV-002 | The refile report counted extra-label mails as refiled | Fixed in #195 |
| REV-003 | The explanation block on the Categories page pointed at a button R1 does not have | Fixed in #196 |
| REV-005 | The model calls per day looked exact | Fixed in #195: the report says "at least" |
| REV-006 | Unused plan creation code | Fixed in #195: removed |
| REV-007 | Missing tests for quiet hours, the hourly cap and crashes of always-notify alerts | Fixed in #195 |
| Follow-up | No database CHECK on the size of `upload_preview.content` | Follow-up migration in `mail-triage`; the api limits the file to 256 KiB meanwhile |
| Follow-up | The alert sentence "urgency read by the model" is fixed text, but a sender-rule mail in a ticked category gets no model call | Found while writing the documentation; to be corrected in a follow-up |
| Known | The downgrade of migration 0024 is lossy by nature (kinds, ticks, senders, instructions and previews are dropped) | Accepted |

Pull requests #194, #195 and #196 were open with green checks when this record was written; they must be merged before release R1.

## Acceptance criteria

The criteria of R1 are AC-1 to AC-40, AC-44, AC-54 to AC-56, AC-58, AC-60 to AC-68 (see the Releases section of the spec). The matrix of criterion, test and layer is in the unit files under `docs/plans/label-structure/`. This record does not repeat it. Criteria of R2 (AC-41 to AC-43, AC-45 to AC-53, AC-57, AC-59) are built in release R2; see the second part.

AC-63 is met in part: the success numbers show the share filed by a sender rule, the model calls per day (a lower bound), the always-notify alerts and the share under "Other"; the Move-back rate of system-approved items is absent until R2, because system approval arrives with R2.

## Known limits

- **Model calls per day is a lower bound.** Urgency-only calls on sender-rule mail are not counted, because no ledger of calls is kept; the report says "at least".
- **Move-back rate.** Absent until R2 (AC-63 above).
- **Browser and backend together.** The real clipboard and file download, and the upload against a real backend, are covered only by the prod-like e2e specs. They are not covered by unit tests with stubs.
- **No screenshots.** The user guide page has no screenshots; none were generated for this feature. The page describes the screens in words.
- **Reference authorisation.** The generated API reference shows every operation as public because the OpenAPI document declares no security scheme; the API guide explains the real access (session, CSRF token and `Origin`).
- **Personal names.** The user reviews the documents for personal names (the user's own mailbox structure was the source of the example and the golden fixture, anonymised). This review is not done.
- **`archiveLabel`.** Stored but without effect in R1 (RED-004); R2 makes it effective.
- **Old mail.** No button re-sorts old mail in R1 (D12); the user guide says so.

## Architecture

The architecture is reconciled with what was built. The design (ADR-0053 to ADR-0059) fixed the components and the dependencies; no dependency changed. What changed in the model (`docs/architecture/model.json` and the written parts of `docs/architecture/README.md`):

- Migrations 0023 to 0028 of the agent chain: the v2 limits of the category checks (0023, ADR-0053); kinds, ticks, senders, list settings, upload previews and filing source, additive (0024, ADR-0053, ADR-0058); the filing code on `topic_id` with the old column dropped (0025); alert causes, `by_rule` and the verified domain (0026, ADR-0057, ADR-0054); `categories.sender_skip` (0027); the list audit with kinds, ticks, senders and general instructions (0028).
- `categories.sender_skip` is not in the design. It is an agent-owned table derived from the filing records, so that the api can read a count per list entry without any right on the agent-owned filing table. It holds list entries and counts, never a sender address or subject, and is removed after 90 days without a skip.
- An upload preview lives 15 minutes and is removed an hour after it expires (the design said one hour).
- The README names the schema `categories` and its writers, and links ADR-0053 to ADR-0059. The diagrams were not changed.

ADRs: ADR-0053 (category contract v2), ADR-0054 (sender rules and the authenticated sender), ADR-0055 (judging with topic, extra label and the urgency-only call), ADR-0057 (the always-notify alert), ADR-0058 (YAML upload as an input boundary). ADR-0056 (two plans) and ADR-0059 (archive label name in the list) belong to R2 and are in its architecture section. ADR-0054 and the plan of U-10 carry the wording of the alert after the challenge.

## Approvals

| Date | Decision |
| --- | --- |
| 2026-11-21 | Spec revision 2 approved by the user; AR-1, AR-2 and AR-3 accepted; open points 1 to 4 answered |
| Not given | Decision on RED-004 (`archiveLabel` before R2) and on RED-008 |
| Not given | Approval of release R1 for production |

## Deploy

Pending: local Docker deploy requested by the owner after merge.

## Release R2: review record (archive label, sort everything again, tips)

Release R2 is units 18 to 27 and unit 39 of the plan (unit 39 was added during the build, see the plan index). It is built on the feature branch `feature/INT-008/label-structure` and lands in one pull request for the feature. The documentation of phase 8 is this record, the [user guide](../user-guide/label-structure.md), the [API guide](../api/README.md) and the reconciled architecture. With R2 all of the spec is built; what is not delivered is listed under "Known limits of R2".

## R2 gates

| Phase | Result | Evidence |
| --- | --- | --- |
| 1 Spec | Revision 2, approved 2026-11-21; R2 criteria AC-41 to AC-43, AC-45 to AC-53, AC-57 and AC-59 | `docs/specs/label-structure.md` |
| 2 Threat model | LS-8 to LS-12, LS-14, LS-16 and LS-18 cover R2; amended after the R2 challenge | `docs/security/label-structure-threat-model.md` |
| 3 Design | ADR-0056 and ADR-0059 accepted with the design | `docs/design/label-structure-design.md` |
| 4 Plan | Units 18 to 27, and unit 39 added while starting unit 26 | `docs/plans/label-structure/` |
| 5 Build, test first | Units built on unit branches, each with its failing test commit first, and landed in the feature branch | `git log` of the feature branch |
| 6 Challenge | Red team and code review ran on the R2 code; repair rounds A and B merged into the feature branch | "R2 challenge" below |
| 7 Verify | One feature pull request and one CI run for the whole of R2. Pull request: to be filled when opened. CI result: to be filled when the run ends. I did not run the prod-like e2e specs for this record (no Docker) | "Known limits of R2" |
| 8 Finish | User guide, API guide, threat model, architecture and this record updated; the spec stays `status: done` | `node scripts/docs.mjs check`, `node scripts/architecture.mjs check` |
| 9 Release | Not started | "R2 approvals and deploy" below |

## R2 units

| Unit | What | Component |
| --- | --- | --- |
| U-18 | The agent adopts, creates and renames the archive label by id after any running plan; the environment setting is removed | mail-triage |
| U-19 | `archiveLabel` on the list, the upload and the export | api |
| U-20 | Migration 0029: `resort_request`, plan kind, request and threshold, item pairs, `request_resort` and `approve_system_plan` | mail-triage |
| U-21 | `POST /api/resort-requests` and `GET /api/resort-requests/latest` | api |
| U-22 | Plan build v2: pair targets, confidence and the scope | mail-triage |
| U-23 | Two plans, system approval, apply, the notice and cancel | mail-triage |
| U-24 | Tips per category with the sender suggestion rules | mail-triage |
| U-25 | The sort-again controls and the archive label field | web |
| U-26 | Review moves with pairs, full names and tips | web |
| U-27 | The R2 journey with three viewports and axe | web |
| U-39 | The review plan shows pairs, confidence, tips and the auto summary | api |

Repairs on the way: the upload preview says when the archive label changes (`archiveLabelChanged`, in the web app of U-16); the runner wiring test of U-18 passes the archive label; the repair rounds of the challenge are below.

## R2 challenge

The outcome per finding is also in the threat model ("Outcome of the R2 challenge").

| Finding | What | Decision |
| --- | --- | --- |
| RED-R2-001 | The system approval could apply at once | Fixed: it always waits the delay (at least a minute) |
| RED-R2-002 | A tip could keep disguised markup or a recommended sender | Fixed: NFKC, cleaned until stable, only code writes the suggested sender |
| RED-R2-003 | The system approval was audited as `telegram` | Fixed: channel `system` |
| RED-R2-004 | Decide and approve could act on an `auto` plan | Fixed: only a `review` plan |
| RED-R2-005 | Sent mail was in scope | Fixed: out of scope |
| RED-R2-006 | More than one archive name rule | Fixed: one rule in `category-policy` |
| RED-R2-007 | The archive label is found by name; a rename in Gmail makes a new empty label | Accepted limitation; follow-up: store the id |
| REV-001 | Three stale tests | Fixed |
| REV-002 | The move-back rate of system-approved items | Delivered (a lower bound) |
| REV-003 | Two copies of the archive rule | Fixed |
| REV-004 | Missing tests | Added |
| REV-005 | Large modules `resort_apply`, `pg_resort` and `resort_build` | Follow-up: split them |

## Decisions taken while building

- **Plan items below 60 % confidence are kept.** The agent does not drop them, so the threshold of the user (50 to 100) decides what moves and what is reviewed.
- **A file without `archiveLabel` keeps the stored name.** The upload preview and the confirm use the stored name; `archiveLabelChanged` is true only when the file gives another one. This also settles RED-004 of R1: the field is now used and no longer ignored.
- **The system plan always waits the delay** (RED-R2-001), also for a small plan.
- **A double post of a request is refused.** One request is stored while no plan or request is open (409).
- **24-hour counting.** Mail that moves on its own counts toward the rolling 24 hours of ADR-0047, like an approval by the user.
- **Channel `system`.** A fourth channel of `plan_approval` and `apply_audit`, a constant of `approve_system_plan`, not derived from the session role.

## Known limits of R2

- **No Cancel in the web app.** Cancel, Move back and Lock are in Telegram only; the web page says so.
- **The agent is not in the prod-like e2e stack.** The R2 journey seeds the plans with SQL. The Gmail apply and the archive label rename are proven by the agent tests only.
- **Failed items** are not counted in the `auto` summary of the review plan.
- **Model calls per day** (tips included) is a lower bound.
- **The archive label** is found by name; a rename in Gmail creates a new, empty label (RED-R2-007).
- **No screenshots** for the R2 screens; the user guide describes them in words.
- **The template and example files** served by the api still say that `archiveLabel` has no effect before release 2 (`packages/category-policy/template/`). That is code, not documentation; it is a follow-up.
- **Personal names.** The review of the documents for personal names by the user is still not done.
- **Large modules.** `resort_apply`, `pg_resort` and `resort_build` are to be split (REV-005).

## R2 architecture

The design (ADR-0056, ADR-0059) fixed the components; no dependency changed. The model (`docs/architecture/model.json`) and the written parts of `docs/architecture/README.md` now name:

- Migration 0029 (ADR-0056): `categories.resort_request`; `plan.kind`, `plan.request_id` and `plan.threshold`; one open plan per mailbox and kind; on `plan_item` the old and new pair, `confidence_pct`, `decision_source` and `tip`; the `SECURITY DEFINER` functions `request_resort` (api role) and `approve_system_plan` (agent role only, SQLSTATE 42501 for the api); the approval channel `system`; `approve_plan` and `record_decision` limited to the `review` plan.
- The agent: two plans, tips and the archive label sync (ADR-0059: the environment setting `ARCHIVE_LABEL` is gone, the name lives in `list_settings`).
- The api: the sort-again request and `archiveLabel`; it still never approves system items.

ADRs: [ADR-0056](../memory/decisions/ADR-0056-resort-on-request-threshold-and-two-plans.md) (re-sort on request, two plans, system approval; supersedes decisions 1 to 4 of ADR-0046) and [ADR-0059](../memory/decisions/ADR-0059-archive-label-name-in-the-list.md) (archive label name in the list; supersedes ADR-0052).

## R2 approvals and deploy

| Date | Decision |
| --- | --- |
| Not given | Approval of release R2 for production |
| Not given | Decision on the follow-ups: store the archive label id, split the large modules |

Deploy: pending, local Docker deploy requested by the owner after merge.
