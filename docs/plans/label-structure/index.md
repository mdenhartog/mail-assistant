---
intent: INT-008
feature: label-structure
spec: docs/specs/label-structure.md
---

# My own label structure, sender rules and always-notify

The plan for `docs/specs/label-structure.md` (revision 2, approved) and `docs/design/label-structure-design.md`. 38 units in two releases: R1 (units 01 to 17, 28 to 38) and R2 (units 18 to 27). Unit 35 (the ingress body limit of the upload route) was found while building unit 12 and lands in the same pull request as it. Units 33 (the ingress body limit of the Helm chart) and 34 (the web app sends the v2 list fields) were found while building unit 11 and land in the same pull request as it, so that `main` stays green and the edge does not refuse a v2 list. Units 36 to 38 carry the per-entry counts of skipped (not authenticated) sender-rule mail on the Categories page (K11 of the round table, AC-16): the agent records them in a derived table (36), the api returns them (37) and the web app shows them (38). Unit 32 was split out of unit 08. Units 28 to 31 were added while building unit 02: its rebuild of `category-policy` changes rules that the agent, the api and the web app each test or copy (units 28, 29 and 30), and the database check constraints still hold the old limits (unit 31), so they must land in the same pull request as unit 02 to keep `main` green. Every unit belongs to one component of `docs/architecture/model.json`. R2 starts after R1 is released (units 18 and 20 depend on unit 17).

## Units

| Unit | Name | Layer | Depends on | Parallel | Wave |
|---|---|---|---|---|---|
| [U-label-structure-01](U-label-structure-01.md) | Agent test fakes for headers, calls and fixtures | backend | — | yes | 1 |
| [U-label-structure-02](U-label-structure-02.md) | category-policy v2: names, kinds, limits, archive rule, confidence scale | backend | — | yes | 1 |
| [U-label-structure-06](U-label-structure-06.md) | Remove the automatic plan (R1) | backend | — | yes | 1 |
| [U-label-structure-28](U-label-structure-28.md) | The agent follows the policy v2 name rules | backend | U-label-structure-02 | yes | 1 |
| [U-label-structure-31](U-label-structure-31.md) | Relax the category check constraints to the v2 limits | backend | U-label-structure-02 | yes | 1 |
| [U-label-structure-29](U-label-structure-29.md) | The api follows the policy v2 name rules and limits | backend | U-label-structure-02, U-label-structure-31 | yes | 1 |
| [U-label-structure-30](U-label-structure-30.md) | The web app follows the policy v2 name rules | web | U-label-structure-02 | yes | 1 |
| [U-label-structure-03](U-label-structure-03.md) | category-policy v2: sender entries, the matcher and the refused domains | backend | U-label-structure-02 | yes | 2 |
| [U-label-structure-05](U-label-structure-05.md) | Migration for contract v2 (R1) | backend | U-label-structure-02 | yes | 2 |
| [U-label-structure-07](U-label-structure-07.md) | One authenticated-sender verifier (R1) | backend | U-label-structure-01 | yes | 2 |
| [U-label-structure-04](U-label-structure-04.md) | category-policy v2: the YAML schema, the template and the fixtures | backend | U-label-structure-02, U-label-structure-03 | yes | 3 |
| [U-label-structure-32](U-label-structure-32.md) | The filing code uses topic, extra label and source | backend | U-label-structure-05 | no | 3 |
| [U-label-structure-08](U-label-structure-08.md) | Sender-rule filing (R1) | backend | U-label-structure-01, U-label-structure-02, U-label-structure-03, U-label-structure-05, U-label-structure-07, U-label-structure-32 | no | 4 |
| [U-label-structure-09](U-label-structure-09.md) | Judging v2 and the urgency-only call (R1) | backend | U-label-structure-01, U-label-structure-02, U-label-structure-05 | no | 3 |
| [U-label-structure-11](U-label-structure-11.md) | Api: the category list v2 (R1) | backend | U-label-structure-02, U-label-structure-03, U-label-structure-05 | yes | 3 |
| [U-label-structure-33](U-label-structure-33.md) | The ingress body limit of the list save fits the v2 list | infra | U-label-structure-11 | yes | 4 |
| [U-label-structure-34](U-label-structure-34.md) | The web app round-trips the v2 list fields | web | U-label-structure-11 | yes | 4 |
| [U-label-structure-10](U-label-structure-10.md) | The always-notify alert (R1) | backend | U-label-structure-08, U-label-structure-09 | yes | 4 |
| [U-label-structure-12](U-label-structure-12.md) | Api: upload, preview, confirm and restore (R1) | backend | U-label-structure-04, U-label-structure-11 | no | 4 |
| [U-label-structure-13](U-label-structure-13.md) | Api: export and template (R1) | backend | U-label-structure-04, U-label-structure-11 | no | 4 |
| [U-label-structure-15](U-label-structure-15.md) | Web: the Categories list and the edit view (R1) | web | U-label-structure-11 | yes | 4 |
| [U-label-structure-35](U-label-structure-35.md) | The ingress body limit of the upload route | infra | U-label-structure-12 | yes | 5 |
| [U-label-structure-14](U-label-structure-14.md) | Audit, success report and cross-cutting tests (R1) | backend | U-label-structure-08, U-label-structure-09, U-label-structure-10 | yes | 5 |
| [U-label-structure-16](U-label-structure-16.md) | Web: upload, preview, restore and export (R1) | web | U-label-structure-12, U-label-structure-13, U-label-structure-15 | no | 5 |
| [U-label-structure-17](U-label-structure-17.md) | Web: accessibility and end-to-end journey for R1 | web | U-label-structure-15, U-label-structure-16, U-label-structure-38 | no | 7 |
| [U-label-structure-36](U-label-structure-36.md) | The agent records skipped sender rules (R1) | backend | U-label-structure-08, U-label-structure-10 | no | 5 |
| [U-label-structure-37](U-label-structure-37.md) | Api: the per-entry skipped counts (R1) | backend | U-label-structure-11, U-label-structure-36 | no | 6 |
| [U-label-structure-38](U-label-structure-38.md) | Web: the skipped count beside a sender entry (R1) | web | U-label-structure-15, U-label-structure-37 | no | 7 |
| [U-label-structure-18](U-label-structure-18.md) | Archive label: the agent adopts, creates and renames it (R2) | backend | U-label-structure-05, U-label-structure-17 | yes | 7 |
| [U-label-structure-20](U-label-structure-20.md) | The sort-again request, plan columns and the approval functions (R2) | backend | U-label-structure-05, U-label-structure-17 | yes | 7 |
| [U-label-structure-19](U-label-structure-19.md) | Api: the archive label setting (R2) | backend | U-label-structure-11, U-label-structure-18 | yes | 8 |
| [U-label-structure-21](U-label-structure-21.md) | Api: the sort-again request routes (R2) | backend | U-label-structure-11, U-label-structure-20 | no | 8 |
| [U-label-structure-22](U-label-structure-22.md) | Plan build v2: pair targets, confidence and the scope (R2) | backend | U-label-structure-08, U-label-structure-20 | yes | 8 |
| [U-label-structure-23](U-label-structure-23.md) | Two plans, system approval, apply and cancel (R2) | backend | U-label-structure-20, U-label-structure-22 | no | 9 |
| [U-label-structure-25](U-label-structure-25.md) | Web: the sort-again controls and the archive label field (R2) | web | U-label-structure-19, U-label-structure-21 | yes | 9 |
| [U-label-structure-24](U-label-structure-24.md) | Tips per category (R2) | backend | U-label-structure-23 | yes | 10 |
| [U-label-structure-26](U-label-structure-26.md) | Web: Review moves with pairs, full names and tips (R2) | web | U-label-structure-21, U-label-structure-24 | yes | 11 |
| [U-label-structure-27](U-label-structure-27.md) | End-to-end journey for R2 | web | U-label-structure-25, U-label-structure-26 | no | 12 |

## Build order

R1:

1. Wave 1 — in parallel: U-label-structure-01, U-label-structure-02, U-label-structure-06; units 28, 29, 30 and 31 are built on top of the branch of unit 02 (28, 30 and 31 in parallel; 29 needs the constraints of 31 for its limit tests) and one pull request carries units 02, 31, 28, 29 and 30, one commit group per unit
2. Wave 2 (after wave 1) — in parallel: U-label-structure-03, U-label-structure-05, U-label-structure-07
3. Wave 3 (after wave 2) — U-label-structure-04 and U-label-structure-11 in parallel; U-label-structure-08 and U-label-structure-09 one at a time (both in the filing flow)
4. Wave 4 (after wave 3) — U-label-structure-10 and U-label-structure-15 in parallel; U-label-structure-12 and U-label-structure-13 one at a time (both change the OpenAPI document)
5. Wave 5 (after wave 4) — U-label-structure-14, U-label-structure-16 and U-label-structure-36 (at most two at a time; 14 and 36 both change the agent database, so one at a time)
6. Wave 6 (after wave 5) — U-label-structure-37 (it changes the OpenAPI document)
7. Wave 7 (after wave 6) — one at a time: U-label-structure-38, then U-label-structure-17; then the R1 release (phase 8 documentation, phase 9)

R2 (after R1 is released):

1. Wave 7 — in parallel: U-label-structure-18, U-label-structure-20
2. Wave 8 (after wave 7) — U-label-structure-19 and U-label-structure-22 in parallel; U-label-structure-21 one at a time (both api units change the OpenAPI document)
3. Wave 9 (after wave 8) — U-label-structure-25 in parallel; U-label-structure-23 one at a time
4ve 10 (after wave 9) — U-label-structure-24
5ve 11 (after wave 10) — U-label-structure-26
6ve 12 (after wave 11) — one at a time: U-label-structure-27; then the R2 release

Test infrastructure first (unit 01), the migration before anything reads the new columns (units 05 and 20), and the automatic plan removal (unit 06) in the first wave so that no upload of 43 labels can start a plan.

## Placement

| Responsibility | Component | Why here | Alternatives rejected | ADR |
|---|---|---|---|---|
| Name rules per segment, kinds, limits, refused domain lists, sender entry rules, the pure sender matcher, the YAML schema and the template file | `category-policy` | Pure rules that the agent and the api must apply identically; already the home of the contract (ADR-0042). | In the api only (the agent filing would drift); in `schedule-policy` (wrong responsibility) | ADR-0053 |
| Authenticated-sender verifier (`authenticated_from_domain`) | `mail-triage` | Only the agent reads mail headers; pinned mail already needs the same check. | A copy for sender rules (two weaker parsers) | ADR-0054 |
| Sender-rule filing, `Judgement` v2, the urgency-only call, general instructions in the prompt | `mail-triage` | It owns judging and is the only component with Gmail and model access. | The api (no Gmail, no model) | ADR-0055 |
| Always-notify alert decision and text | `mail-triage` | It owns every alert and Telegram dialogue. | The Telegram gateway (`chat-gateway` is an unused scaffold) | ADR-0057 |
| Upload parsing, preview, confirm, export, template, restore | `api` | Parses untrusted input at the trust boundary and owns list writes; rules come from `category-policy`. | The agent (no web surface); the browser (no trust) | ADR-0058 |
| `request_resort` and the sort-again request row | `postgres` function, called by `api` | The components meet only in PostgreSQL (ADR-0041); a function is the api's only write path (ADR-0047). | An api call to the agent (ADR-0041) | ADR-0056 |
| Two plans, threshold split, `approve_system_plan`, tips, apply | `mail-triage` and a `postgres` function | The agent owns plans and Gmail effects; the approval function is database code the agent role alone may run. | Api approval (bypasses review) | ADR-0056 |
| Archive label name (stored), validation, adopt, rename by id | stored in `postgres` (`list_settings`), handled by `mail-triage`, validated by `category-policy` | One validation; the agent is the only Gmail writer. | An environment setting (rejected by the user) | ADR-0059 |
| Categories and Review moves screens | `web` | The only user interface for settings. | Telegram (D1 of `mail-categories`) | — |
| Success report (D22) | `mail-triage` | It already compares filings with current labels. | A new component | ADR-0053 |
