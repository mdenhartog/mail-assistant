---
feature: mail-triage
spec: docs/specs/mail-triage.md
threat-model: docs/security/mail-triage-threat-model.md
intent: INT-001
status: draft
date: 2026-11-08
approver: Marco
---

# Design: mail-triage

Decisions: ADR-0017 (Anthropic API), ADR-0018 (accepted risks), ADR-0019 (architecture). No screens exist in this feature, so there are no design tokens and no prototype (ADR-0009).

## Architecture

```text
 Gmail  ◄── poll / label / send ──┐
                                  │      ┌───────────── agents/mail-triage (one replica) ─────────────┐
 Anthropic API ◄─ structured ─────┼──────┤  Gmail adapter   Model adapter   Telegram adapter   DB adapter │
                                  │      │        └──────────┬──────────────────┘                  │     │
 Telegram ◄── long polling ───────┘      │                 CORE (pure logic)                      │     │
   ▲  buttons, replies                   │  urgency policy · alert state machine · quiet hours ·  │     │
   │                                     │  reminders · daily overview                            ▼     │
 Marco                                   └──────────────────────────────────────────────────── PostgreSQL ┘
```

Trust boundaries (from the threat model): internet ↔ cluster; adapters ↔ core; **mail text is untrusted input** and only reaches the model adapter, whose only output is a validated object.

## Core behaviour

1. **Poll loop** (every 60 s, configurable): list new mails since the stored history id; for each unseen Gmail message id insert a `mail_item` row (unique on message id, so a mail is processed at most once).
2. **Judge**: send subject, sender and trimmed text to the model. The result must match this schema or it is rejected (AC-18): `category` (existing label or a proposed new name), `urgent` (boolean), `reason` (short), `summary` (short), `confidence`. A rejected or low-confidence result is treated as needs-attention (urgent), never as ignorable.
3. **File**: apply exactly one category label and remove the inbox label as the mail is "moved". New label names must match `Assistant/<name>` and the maximum of 15 (AC-13).
4. **Alert**: if urgent and not in quiet hours, send the Telegram alert and set the alert state to `open`; in quiet hours set it to `held` and send it with the other held alerts when quiet hours end (AC-32).
5. **Marco's choice** (inline buttons on the alert):
   - **Reply**: Marco types text. The agent writes the mail and stores a draft with a hash of recipient, subject and body. Telegram shows the draft with Send / Edit / Cancel. Only Send with the matching, unused, unexpired confirmation sends (AC-6, AC-20). Then the alert is `closed`.
   - **Remind me later**: the bot asks for hours or "tomorrow"; state `snoozed` with a due time; at that time one new alert is sent (AC-9).
   - **No more reminders**: state `closed` (AC-10).
6. **Daily overview** at 18:00 (configurable): counts per category and the mails the agent was unsure about; nothing is sent when nothing was filed (AC-31).
7. **Failures**: per-mail retry with a limit, then one error notice and the queue continues (AC-27); a daily model budget and an alerts-per-hour cap (AC-26).

## Alert state machine

```text
 (new urgent mail) ──► held ──(quiet hours end)──► open ──► closed
                  └──────────────────────────────► open ──► snoozed ──(due)──► open
                                                    open ──► drafting ──► confirming ──► closed
                                                                 └── cancel ──► open
```

## Data model (PostgreSQL, Alembic migrations)

| Table | Purpose | Notes |
|---|---|---|
| `mail_item` | one row per Gmail message | `gmail_message_id` unique; label applied; `urgent`; `confidence`; no body stored |
| `alert` | state of an alert per mail | state, due time, Telegram message id, quiet-hours hold flag |
| `draft` | reply draft awaiting confirmation | hash of recipient, subject, body; expiry; used flag; the text itself |
| `audit_log` | what happened and who confirmed | ids, timestamps, hashes, model decision and reason; no bodies (AC-22) |
| `oauth_token` | Gmail refresh token | encrypted; key from the secret store (AC-25) |
| `poll_state` | last history id | and the single-replica lock |

## Gmail operations allow-list (phase 3b contract)

Google publishes the Gmail API, so the contract here is the set of calls our wrapper exposes (AC-28). Scopes stay `gmail.readonly`, `gmail.send`, `gmail.modify` (ADR-0011).

| Wrapper operation | Gmail call | Notes |
|---|---|---|
| `list_new(history_id)` | `users.history.list`, `users.messages.list` | paginated; `labelIds=INBOX`; excludes SENT (AC-29) |
| `fetch(message_id)` | `users.messages.get` | `fields` limited; format `metadata` plus `full` text part; attachments never fetched (AC-23) |
| `ensure_label(name)` | `users.labels.list`, `users.labels.create` | `Assistant/` prefix only |
| `file(message_id, label)` | `users.messages.modify` | add one category label, remove `INBOX` |
| `send_reply(draft)` | `users.messages.send` | same thread, to `From`; blocked for automatic senders (AC-29) |

There is no wrapper operation for trash, delete or spam. A test fails if the wrapper module references those Gmail methods.

## Configuration and secrets

| Name | Where | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | `.env` / Kubernetes secret | never logged; client redacts |
| `TELEGRAM_BOT_TOKEN` | `.env` / Kubernetes secret | sits in API URLs, so HTTP logging redacts URLs (AC-24) |
| `TELEGRAM_ALLOWED_USER_ID`, `TELEGRAM_ALLOWED_CHAT_ID` | config | Marco only (AC-15) |
| Gmail OAuth client id and secret | secret | one-time consent run for the owner stores the encrypted refresh token |
| Model ids (small, large) | config | not literals |
| Quiet hours, overview time, poll interval, daily model budget, alerts per hour | config | defaults from spec C1, C7 |

ADR-0008 describes a web login; this feature does not need it. The owner gives consent once with a small command-line flow, and the agent uses the stored refresh token.

## Testing approach

- Core: pure unit tests, test-first, no network.
- Each adapter against a fake of its port; Gmail and Telegram with recorded responses; no real calls in unit tests.
- Prompt-injection samples as fixtures (AC-19); schema-reject tests (AC-18).
- A test that scans the Gmail wrapper for trash, delete and spam (AC-28).
- Playwright and accessibility checks do not apply (no UI); end-to-end uses a Gmail test account and a test bot, run manually before release.

## Out of this design

Web screens, multiple users, calendar, attachments, other mail providers.

## Open for Marco

- Confirm quiet hours 23:00–07:00 and the overview at 18:00 (spec C7).
- Confirm that `chat-gateway` and `agents/assistant` stay unused and unchanged for now (ADR-0019).
