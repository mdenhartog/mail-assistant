---
id: ADR-0058
title: "YAML upload and export: a hardened input boundary with a bound preview"
status: proposed
area: security
tags: [label-structure, api, yaml, input-validation, csrf]
date: 2026-11-21
guardrails: [guardrail-fastapi, guardrail-pydantic, guardrail-python, guardrail-sqlalchemy-alembic]
---

## Context

The user loads the whole category list from a YAML file (D6) and exports it in the same format; a template is shipped (D21). A file is untrusted input (threat model LS-5, LS-6, LS-7, LS-17): alias bombs, object tags, duplicate keys, YAML 1.1 booleans, replayed or cross-site confirmations, and a mistaken file that silently replaces the list.

## Decision

1. The api accepts YAML only, with `schema: 1`, at most 256 KiB (checked before parsing), through a safe loader whose event stream is checked first: every anchor, alias, merge key and tag is refused, duplicate keys are refused, unknown fields are refused, depth and node counts are limited, and words such as `no`, `on` and `yes` stay strings. The schema and every rule are those of `category-policy` (ADR-0053); the dependency is PyYAML's `safe_load` behind that event check (licence and maintenance checked in phase 4).
2. Errors name the line and field (`line 12, senders[3]`) and never the value; every problem is listed; nothing is stored on any error.
3. **Preview.** An upload creates a row in `upload_preview` (api-writable, `mailbox_id`, `id`, session digest, file hash, base list version, normalised content, `expires_at` after 15 minutes, `used_at`); the response is the preview (added, changed, removed) and the id. The confirm call needs the same session, the same hash, an unexpired and unused id and an unchanged list version, otherwise 409 and nothing is stored; a double confirm makes one version. The table is purged by `purge_expired()` (ADR-0047).
4. Upload and confirm need the session, the CSRF token and a matching `Origin` (403 otherwise) and share the hourly limit of a list save (429 above it).
5. A confirm writes one list version (ADR-0053) with an audit record and the Telegram change notice with an Undo token (ADR-0033). "Restore previous version" writes a new version equal to the previous one.
6. The export is a session-protected GET sent as an attachment (`mail-categories.yaml`) with `nosniff` and `no-store`, with the same fields as the upload and `schema: 1`. The template and an example file ship in `packages/category-policy/template/` and are served by the api.
7. Canary strings (descriptions, senders, instructions, file content) are searched for in the application log, the access log, a Sentry stub, a Telegram stub and the audit rows.

## Consequences

- One new table (`upload_preview`) and four routes (upload, confirm, export, template) plus restore, added to the route allow-list.
- A new dependency (PyYAML) in `backend/`.
- Another person who installs the agent gets the same file and template (D21); the future skill of INT-009 produces this format.

## Alternatives

- Parse with a library that has no unsafe features (a JSON upload): the user chose YAML (D6, U10). Rejected.
- Keep the preview in process memory: lost on restart and not shared between replicas. Rejected.
- Skip the preview binding: a replayed or cross-site confirm could replace the list. Rejected (LS-6).
