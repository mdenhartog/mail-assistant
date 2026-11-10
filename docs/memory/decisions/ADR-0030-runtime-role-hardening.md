---
id: ADR-0030
title: "Runtime role hardening: least-privilege grants, server-derived audit actor, SCRAM set by the client"
status: accepted
area: security
tags: [mail-triage, postgresql, settings, audit, scram, mutation-testing]
date: 2026-11-10
guardrails: [guardrail-sqlalchemy-alembic, guardrail-python, guardrail-kubernetes]
---

## Context

The phase-6 challenge round of INT-002 (red-team, code review, security review) found that the runtime role of ADR-0025 is still wider than the code needs, and that the migration job handles the runtime password carelessly.

- `grants.sql` gives the runtime role `UPDATE` and `DELETE` on every mail-triage table. The code only inserts into `audit_log` and only deletes from `conversation`.
- The audit trigger on `settings.schedule` copies `updated_via` and `updated_by` from the row, so the writer chooses its own channel and actor. The version is not checked by the database either.
- The migration job sends `CREATE/ALTER ROLE … PASSWORD '<clear text>'`. A failing statement is written to the server log with the password in it, and the `?ssl=` part of `DATABASE_OWNER_URL` is dropped when the job connects.

## Decision

1. **Grants per table, by what the code does.** `audit_log` is append-only (`SELECT, INSERT`). `DELETE` only on `conversation`. `UPDATE` only on tables the code updates. Every denied statement is a test in `tests/db` and in the CI `runtime-role` job.
2. **The database decides who wrote a settings change.** A trigger owned by the owner role enforces `version = old.version + 1` and sets `updated_at`. The channel is derived from `session_user` (the agent role means `telegram`, the web backend role means `web`) and `session_user` is stored in `settings_change`. A row that claims another channel is refused.
3. **The runtime password is hashed on the client.** The migration job computes the SCRAM-SHA-256 verifier itself (random salt, 4096 iterations) and sends only `PASSWORD 'SCRAM-SHA-256$…'`. The clear password never reaches the server, its log or `pg_stat_activity`. The job also sets `NOREPLICATION NOBYPASSRLS`, fails when the runtime role has any role membership, and passes the TLS parameters of `DATABASE_OWNER_URL` on to the connection.
4. **The 85 % mutation criterion runs in CI nightly and on manual start**, not on every pull request (cosmic-ray is slow). A score below 85 % fails the job.

## Consequences

- A leaked runtime credential can no longer rewrite the mail audit trail, forge the channel of a settings change or skip a version.
- The migration job needs a small SCRAM helper (hashlib PBKDF2, tested against a known vector and against a real server login).
- The web backend role of `web-settings` gets its own login role and its own grants; the trigger already knows how to tell it apart.
- A regression in the boundary logic is seen within a day, not on the pull request that causes it.

## Alternatives

- TLS enforcement only: simpler, but the password still reaches the server in clear text and can end up in its log. Rejected by the owner.
- Mutation check on every pull request: strictest, but slows every change to the two modules. Rejected by the owner.
- Trust the application for the audit actor: what exists today; it fails as soon as a second writer appears.
