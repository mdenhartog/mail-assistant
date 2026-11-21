---
feature: label-structure
intent: INT-008
spec: docs/specs/label-structure.md
status: draft
date: 2026-11-21
---

# Design: label structure, sender rules and always-notify

The design of `docs/specs/label-structure.md` (revision 2, approved) on top of the built `mail-categories` design (`docs/design/mail-categories-design.md`). Only what changes is written here. Decisions D1 to D22 are the user's; ADR-0053 to ADR-0059 (proposed) record the design choices.

## Releases

- **R1:** contract v2 and migration (ADR-0053), `category-policy` v2, the single authenticated-sender verifier and sender-rule filing (ADR-0054), judging with topic and extra label and the urgency-only call (ADR-0055), the always-notify alert (ADR-0057), upload, export, template and restore (ADR-0058), removal of the automatic plan, the Categories page, audit, the success report.
- **R2:** `request_resort`, two plans, system approval, tips (ADR-0056), the archive label setting (ADR-0059), the sort-again controls and Review moves changes.

## Placement ("where is this best solved?")

| Responsibility | Component | Why here | Alternatives rejected | ADR |
| --- | --- | --- | --- | --- |
| Name rules per segment, kinds, limits, refused domain lists, sender entry rules, the pure sender matcher, the YAML schema and the template file | `category-policy` | Pure rules that the agent and the api must apply identically; already the home of the contract (ADR-0042). | In the api only (the agent filing would drift); in `schedule-policy` (wrong responsibility) | ADR-0053 |
| Authenticated-sender verifier (`authenticated_from_domain`) | `mail-triage` (`core/`) | Only the agent reads mail headers; pinned mail already needs the same check. | A copy for sender rules (two weaker parsers) | ADR-0054 |
| Sender-rule filing, `Judgement` v2, the urgency-only call, general instructions in the prompt | `mail-triage` | It owns judging and is the only component with Gmail and model access. | The api (no Gmail, no model) | ADR-0055 |
| Always-notify alert decision and text | `mail-triage` | It owns every alert and Telegram dialogue. | Telegram gateway (`chat-gateway` is an unused scaffold) | ADR-0057 |
| Upload parsing, preview, confirm, export, template, restore | `api` | Parses untrusted input at the trust boundary and owns list writes; rules come from `category-policy`. | The agent (no web surface); the browser (no trust) | ADR-0058 |
| `request_resort` and the sort-again request row | `postgres` function, called by `api` | The components meet only in PostgreSQL (ADR-0041); a function is the api's only write path (ADR-0047). | An api call to the agent (ADR-0041) | ADR-0056 |
| Two plans, threshold split, `approve_system_plan`, tips, apply | `mail-triage` + `postgres` function | The agent owns plans and Gmail effects; the approval function is database code the agent role alone may run. | Api approval (bypasses review) | ADR-0056 |
| Archive label name (stored), validation, adopt, rename by id | stored in `postgres` (`list_settings`), handled by `mail-triage`, validated by `category-policy` | One validation; the agent is the only Gmail writer. | Environment setting (rejected by the user) | ADR-0059 |
| Categories and Review moves screens | `web` | The only user interface for settings. | Telegram (D1 of `mail-categories`) | — |
| Success report (D22) | `mail-triage` (the daily AC-46 report) | It already compares filings with current labels. | A new component | ADR-0053 |

No new component, no new external system, no new dependency between components. The model and the overview change only in the responsibilities and owned data of `mail-triage`, `api`, `web`, `category-policy`, `postgres` and `anthropic`.

## Data model delta (schema `categories`, ADR-0053, ADR-0056, ADR-0058)

Every new table has `mailbox_id` first in its keys (ADR-0043). Existing rows get defaults; no list version is inserted.

| Table | Change | Written by | Retention |
| --- | --- | --- | --- |
| `category` | add `kind` (`topic`, `extra`; default `topic`), `notify` (default false) | api, agent (insert only) | with its version |
| `category_sender` | new: `version`, `category_id`, `entry` (lower-case A-label), `is_domain`, `subdomains` | api, agent (insert only, same deferred trigger) | with its version |
| `list_settings` | new: `version`, `general_instructions` (0 to 4 000), `archive_label` | api, agent (insert only) | with its version |
| `filing` | rebuilt: `topic_id`, `extra_id`, `source`, `source_ref` (matched entry), list version, time | agent | 1 year |
| `resort_request` | new, insert-only: `id`, `threshold` (50 to 100), time, actor digest and channel (derived) | `request_resort` | 1 year |
| `plan` | add `kind` (`auto`, `review`), `request_id`, `threshold`; the partial unique index is on `(mailbox_id, kind)` for non-terminal plans | agent | 14 days after terminal |
| `plan_item` | add `old_topic_id`, `old_extra_id`, `new_topic_id`, `new_extra_id`, `confidence_pct`, `decision_source` (`user`, `threshold`), `tip` (text, capped) | agent inserts; decisions through the functions | as before |
| `upload_preview` | new: `id`, session digest, file hash, base version, normalised content, `expires_at`, `used_at` | api | purged after 1 hour by `purge_expired()` |
| `filing_alert` (or the existing alert table) | unique key on the mail id so an alert is written once | agent | as the alert table |

Grants: the api role gets `SELECT, INSERT` on `category_sender`, `list_settings` and `upload_preview` (`UPDATE` of `used_at` only), `SELECT` on `resort_request`, and `EXECUTE` on `request_resort`; the agent role gets `SELECT` on `resort_request` and `EXECUTE` on `approve_system_plan`; no runtime role may approve a system plan except the agent role, and the api role gets SQLSTATE 42501 on it. The matrix test of `mail-categories` is extended.

Functions (`SECURITY DEFINER`, non-login owner, pinned `search_path`, revoked from `PUBLIC`): `request_resort(mailbox_id, threshold)` checks the range and that no non-terminal request or `auto`/`review` plan is open; `approve_system_plan(plan_id)` is described in ADR-0056; `purge_expired()` also removes expired `upload_preview` rows.

## State machine delta (owned by the agent, ADR-0056)

The plan states and the item states of ADR-0046 stay. New: a plan has a `kind`; one non-terminal plan per mailbox and kind; an `auto` plan goes `building -> ready -> scheduled` through `approve_system_plan` (no user step) and then `applying -> applied`; a `review` plan follows the existing user path. Cancel, Undo and Lock cancel `scheduled` plans of both kinds. A category removed by an upload moves open plans that target it to `cancelled`. There is no debounce build and no first-start plan.

## API delta (generated OpenAPI; added to the route allow-list)

403 only for the web lock, CSRF and `Origin`; 409 for a version, preview or plan mismatch; problem+json without values; `Cache-Control: no-store`.

| Method and path | Release | Result |
| --- | --- | --- |
| GET and PUT `/api/categories` | R1 | extended with `kind`, `notify`, `senders[]` (`entry`, `subdomains`), `generalInstructions` and (R2) `archiveLabel`; per-entry counts of skipped (not authenticated) mails on GET |
| POST `/api/categories/upload` | R1 | body: the file; returns the preview id and counts (added, changed, removed) with the removed categories |
| POST `/api/categories/upload/{id}/confirm` | R1 | 409 on any binding mismatch; one list version |
| POST `/api/categories/restore-previous` | R1 | a new version equal to the previous one |
| GET `/api/categories/export` and `/template` | R1 | attachments, `nosniff`, `no-store` |
| POST `/api/resort-requests` and GET `/api/resort-requests/latest` | R2 | `{threshold}`; calls `request_resort`; the latest request gives the field's value |

## Agent flows delta

- **Filing (R1):** pinned check (ADR-0048) -> sender rule (`authenticated_from_domain`, then the matcher) -> if matched: file topic and extra, in an unticked category one urgency-only call, in a ticked category none -> else the model with general instructions (ADR-0055) -> `alert_decision` (ADR-0057) -> write the filing record with its source.
- **List change (R1):** as before, plus labels for nested names (`Assistant/<name>`, parents not required), the removal of the debounce build and of the first-start plan, and the archive label handling in R2.
- **Sort again (R2):** reads a new `resort_request`, scans the scope (inbox and `Assistant/` labels; not spam, trash, the archive label or pinned or rejected mail), judges within the budget share, splits the items into an `auto` and a `review` plan, calls `approve_system_plan`, sends one notice with numbers (moves on its own after the delay, waits for review, Cancel, Move back, Lock), builds tips for the `review` plan, applies after `apply_after`.
- **AC-46 report (R1):** adds the success numbers of D22.

## Web (screens: see the spec, section Screens)

Routes `/categories` and `/review`; the Categories page is a collapsed nested list with a full-screen edit view, a sender textarea, upload and export with the preview, the archive label field and the sort-again controls (threshold field, button, texts). Review moves shows full nested names, the tip per category (a link to the category) and the pair (topic, extra). Data only through hooks in `src/api/categories/*.queries.ts` with types from OpenAPI; all states. There is no clickable prototype (the spec decides no; the screens section is the brief). The built `ConfirmDialog` keeps its `tone`.

## Test strategy (summary; the plan in phase 4 maps every criterion to a test)

Unit 1 is the infrastructure: the fake Gmail returns raw headers (several `Authentication-Results`, folded, forged, none, other authserv-id, plus anonymised real headers), a fake model with a scripted confidence that records the call kind (category, urgency-only, tip), YAML fixtures (valid, the anonymised 43-label golden file, hostile files), the fake clock and budget ledger, and a real PostgreSQL role test. Then: `category-policy` v2 and its contract cases (with the mutation gate on the name rules, the matcher, the threshold comparison, the verifier, the alert decision and the YAML limits), the migration, the api list v2, the filing and verifier, the alert, upload and export, the Categories page; then R2. Playwright runs three viewports and axe on both pages; a security suite runs AC-15, AC-19, AC-32, AC-35, AC-36, AC-53, AC-57, AC-59, AC-60 in CI. Time is always a fake clock; concurrency tests use explicit barriers.

## Units (proposal for phase 4, order matters)

1. Test infrastructure and fixtures. 2. `category-policy` v2 and the contract cases. 3. Migration (columns, tables, `filing`, removal of the debounce build). 4. Api list v2, versions, audit. 5. Verifier extraction and sender-rule filing. 6. Judging v2 and the urgency-only call. 7. Always-notify alert. 8. Upload, preview, confirm, export, template, restore. 9. Categories page (R1). **R2:** 10. Archive label in the list and the agent handling. 11. `request_resort`, `resort_request`, the two plans, `approve_system_plan`. 12. Tips. 13. Sort-again controls and Review moves. 14. End-to-end and the success report check.
