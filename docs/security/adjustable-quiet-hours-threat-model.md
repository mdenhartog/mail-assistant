---
feature: adjustable-quiet-hours
intent: INT-002
spec: docs/specs/adjustable-quiet-hours.md
extends: mail-triage-threat-model
status: approved
date: 2026-11-09
approver: Marco
asvs: "5.0"
---

# Threat model: adjustable quiet hours (Telegram)

The web part (login, session, page) is in `web-settings-threat-model.md`.

## Scope

The guided settings conversation in the `mail-triage` agent, the `settings` schema in PostgreSQL (ADR-0025), the stored conversation state (ADR-0026), and the agent reading the settings at each operation. Not in scope: mail handling, judging and alert content (see `mail-triage-threat-model.md`).

## Data classification

| Data | Class | Note |
| --- | --- | --- |
| Quiet hours, overview time, reminder default | internal | They reveal when Marco sleeps or is busy. |
| Time zone | personal data (low) | Reveals where Marco travels. Telegram already carries all alerts (ADR-0018). Not written to logs. |
| Audit record (time, channel, actor, old, new) | personal data (low) | Contains zone values; kept in the database, fixed columns, no free text. |
| Conversation state (nonce, partial answers) | internal | Short-lived, replaced by the next dialogue. |

## Diagram

```text
Telegram user ──[B1: Bot API, allowed user + chat]──► mail-triage agent ──[B2: agent DB role]──► PostgreSQL schema settings
                                                             │
                                          (reads one snapshot per operation; validates; falls back; tells Marco)
```

An archify data-flow diagram is added with the design in phase 3.

## Threats

L = likelihood, I = impact (L/M/H). ASVS references are to ASVS 5.0 chapters.

| id | element | STRIDE | threat | L | I | mitigation | criterion | ASVS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-1 | B1 commands and buttons | S | Another user, or a forwarded or old button, changes settings. | M | H | Every command and button checks the allowed user id and chat id; a button carries a random nonce that must equal the current conversation's; others get nothing or a "card is out of date" answer. | AC-3, AC-4 | V8, V3 |
| T-2 | B1 conversation | T | A pending question is answered with text meant for another dialogue (snooze, reply), or a stale question is answered later; replayed Telegram updates. | M | M | One stored conversation at a time; a new one replaces the old and says so; slash commands first; settings questions expire after 15 minutes (message edited to "Expired"); Cancel always works; replayed update ids are ignored. | AC-5, AC-6, AC-7 | V2 |
| T-3 | B1 free text | T | Typed times or places are used unsafely (injection, path-like names, huge or control input). | L | M | Strict parsing of a short list of time forms; length cap 64; the zone is only taken from the bundled list and the typed text never reaches a zone lookup, a query or a path; queries are parameterised. | AC-8, AC-9 | V1 |
| T-4 | stored values | T | Settings that silence urgent alerts for too long (typo or attacker with access to Telegram). | M | H | Window 1 to 12 clock hours; whole-row validation; confirmation with the full picture (local times, quiet hours in both zones) and Undo; audit record. | AC-10, AC-11, AC-20, AC-21 | V2 |
| T-5 | audit | R | Nobody can tell when or how a value changed, or the trail is altered. | M | M | Append-only audit table filled by a database trigger (time, channel, actor, old, new); runtime roles can only insert. | AC-30 | V16 |
| T-6 | logs | I | The zone (travel location) or a token reaches a log or error. | L | M | Logs carry the key, not the value; existing redaction; a canary zone must never appear in captured logs. | AC-33 | V16 |
| T-7 | B1 | D | A flood of messages or taps. | L | L | Only the allowed user is processed; one conversation at a time; one write per confirmed change. | AC-3, AC-5 | V2 |
| T-8 | settings row | T | Two writers (Telegram, web later) lose each other's change or produce a row that breaks cross-field rules (overview inside quiet hours). | M | H | One row with a version; a write replaces the whole row, validated as a whole, with a version check; the loser is told "changed elsewhere"; CHECK constraints refuse invalid rows even from a direct insert. | AC-29, AC-34 | V2 |
| T-9 | settings row read | D, T | An invalid row, an unreadable table or a slow read stops the agent from alerting correctly, or silently uses Amsterdam times while Marco is abroad. | M | H | The agent validates on read; falls back to the last good values or the defaults within a 2 s timeout; logs the error class; tells Marco once per incident which values are in use. | AC-31, AC-32 | V16 |
| T-10 | database roles | E | The agent's role can change or delete audit rows, or alter the schema at run time. | M | H | A separate owner role runs migrations; the agent role owns nothing and can only insert into the audit table. | AC-30 | V8 |
| T-11 | held and snoozed alerts | T | A change re-times alerts that are already planned, breaking the intent. | M | M | A snoozed alert keeps its UTC due moment; a held alert keeps the release moment it got when held. | AC-24, AC-25, AC-26 | V2 |
| T-12 | wall-clock rules | T | A time in a clock-change gap or a doubled hour makes quiet hours start or end at the wrong moment. | M | M | All scheduling on UTC moments; the rule of ADR-0027; table tests per zone. | AC-28 | V2 |

All six STRIDE types are covered: S (T-1), T (T-2, T-3, T-4, T-8, T-9, T-11, T-12), R (T-5), I (T-6), D (T-7, T-9), E (T-10).

## Accepted risks

| # | Risk | Reason |
| --- | --- | --- |
| R-1 | After Marco's own zone change, alerts fall in the local night of a far place. | This is the purpose (S6); the confirmation shows the local times (AC-20). |
| R-2 | Telegram sees the zone Marco types and the values. | Telegram already sees every alert (ADR-0018). |

## Open questions

1. Source of the city and country list (phase 3, ADR).
2. ADR-0025, ADR-0026 and ADR-0027 are proposed and need Marco's approval with the spec.
