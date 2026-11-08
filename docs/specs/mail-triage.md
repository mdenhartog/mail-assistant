---
feature: mail-triage
intent: INT-001
status: approved
date: 2026-11-08
approver: Marco
---

# Mail triage

## Summary

An agent reads Marco's incoming personal Gmail, files each mail under a category, and warns Marco through Telegram only when a mail needs his immediate attention. From Telegram, Marco answers the alert in one of three ways: reply, remind me later, or stop reminding me. A reply is shown to him for confirmation before anything is sent.

Why: Marco often has no time for his personal mail and therefore sometimes misses mails that matter (INT-001).

## Who it is for

Marco, the single owner of the mailbox. There is no other user and no web screen in this feature.

## Goals

1. Every incoming mail is filed under exactly one category so the mailbox becomes easy to survey.
2. Marco is warned in Telegram when, and only when, a mail needs his immediate attention.
3. Marco can handle an alert from Telegram: reply, remind me later, or stop reminding me.
4. Nothing leaves the mailbox without Marco's explicit confirmation, and nothing is ever deleted.

## Non-goals

- No web or mobile screen (Telegram is the only interface). Therefore no clickable prototype (ADR-0009, phase 3a: no).
- No multi-user support and no other mail provider than Gmail.
- No calendar handling in this feature.
- No rules editor: Marco does not configure categories or urgency by hand.

## Anti-goals (a failure even if it technically works)

- A mail is deleted, trashed or marked as spam by the agent.
- A mail is sent without Marco having confirmed the exact text.
- Marco is flooded with alerts for newsletters, advertising or automatic notifications.
- The same alert repeats on its own until Marco has acted.

## Decisions made by Marco

| # | Decision | Source |
|---|---|---|
| D1 | Categories are chosen by the agent, based on the mail that actually arrives. | INT-001 |
| D2 | A mail may be moved to a category; it may never be deleted. | INT-001 |
| D3 | Alerts go through Telegram only. | INT-001 |
| D4 | A reply typed in Telegram is shown back for confirmation before it is sent. | brainstorm |
| D5 | Per alert Marco has three choices: reply (then no further reminder), remind me later, no more reminders. An informational but important mail falls under "no more reminders". | brainstorm |
| D6 | For "remind me later" Marco chooses each time: after a number of hours he names, or the next day. | brainstorm |
| D7 | "Needs immediate attention" means: a real person asks Marco personally for something and expects an answer; something with a deadline or an appointment; official or financial matters. Newsletters, advertising and automatic notifications are never urgent. | brainstorm (Marco accepted this proposal) |
| D8 | Models are called through the Anthropic API, not Bedrock. This supersedes the model part of ADR-0005 and is recorded as a new ADR in phase 3. | brainstorm |
| D9 | New mail is fetched by polling Gmail (approach A below). | brainstorm |

## My calls (Marco may change these)

- C1: Polling interval is one minute; the target is that a mail is categorised within five minutes of arrival.
- C2: Categories are Gmail labels under one prefix (`Assistant/`). The agent starts with a small set (for example: Needs reply, Appointments, Finance and bills, Orders and deliveries, Newsletters and promotions, Automatic notifications, Social) and may add a new category when none fits, up to a maximum of 15.
- C3: The agent uses a small model first and escalates to a larger one when it is unsure (ADR-0014).
- C4: The reply is addressed to the sender of the mail (or its Reply-To) in the same thread, in the language of the original mail.
- C5: State (processed mails, pending alerts, confirmations, reminders) is kept in PostgreSQL (ADR-0007).
- C6: A mail that Marco has not acted on stays open and is not alerted again until a reminder is due or Marco acts. The agent does not alert twice by itself.

## Behaviour

1. **Fetch.** Every polling interval the agent asks Gmail for mail that arrived since the last run and processes each mail once.
2. **Categorise.** The agent reads the mail, assigns exactly one category label and moves it there. A mail the agent cannot process stays untouched in the inbox and is retried.
3. **Judge urgency.** The agent decides, with a reason, whether the mail meets D7.
4. **Alert.** For an urgent mail the agent sends Marco a Telegram message with sender, subject, a short summary, the reason it is urgent and three actions: Reply, Remind me later, No more reminders.
5. **Reply.** Marco types a reply. The agent writes it as a proper mail and shows Marco the recipient, subject and body. Only after Marco confirms is it sent. Marco may reject or edit it; nothing is sent then and the mail stays open.
6. **Remind me later.** Marco names a number of hours or "tomorrow". At that time the agent alerts again.
7. **No more reminders.** The mail is closed for alerts. It stays in its category.

## Acceptance criteria

Each criterion traces to INT-001 (what I want / must not do / how I will know it works).

| ID | Criterion | Traces to |
|---|---|---|
| AC-1 | **Given** a new mail in the inbox, **when** the agent runs, **then** the mail carries exactly one category label within five minutes of arrival and nothing else about it is changed. | What I want |
| AC-2 | **Given** any mail in any state, **when** the agent runs, **then** it is never deleted, trashed or marked as spam by the agent. | Must not do |
| AC-3 | **Given** a new mail that meets D7, **when** it is processed, **then** Marco receives one Telegram message with sender, subject, summary, reason and the three actions. | What I want; How I will know |
| AC-4 | **Given** a newsletter, advertisement or automatic notification, **when** it is processed, **then** Marco receives no Telegram message. | How I will know |
| AC-5 | **Given** an alert that Marco has not acted on, **when** time passes, **then** no second alert for that mail is sent. | How I will know |
| AC-6 | **Given** an alert, **when** Marco types a reply, **then** the agent shows recipient, subject and body and sends nothing until Marco confirms. | What I want |
| AC-7 | **Given** a shown draft, **when** Marco confirms, **then** the mail is sent in the same thread to the sender, the mail is closed for alerts and no reminder follows. | What I want |
| AC-8 | **Given** a shown draft, **when** Marco rejects it, **then** nothing is sent and the mail stays open. | Must not do |
| AC-9 | **Given** an alert, **when** Marco chooses "remind me later" with a number of hours or "tomorrow", **then** no alert is sent for that mail before that time and one alert is sent at that time. | What I want |
| AC-10 | **Given** an alert, **when** Marco chooses "no more reminders", **then** that mail is never alerted again and stays in its category. | What I want |
| AC-11 | **Given** a Telegram message from any chat other than Marco's, **when** it arrives, **then** it is ignored and nothing is read, sent or changed. | Must not do |
| AC-12 | **Given** Gmail, Telegram or the model is unavailable, **when** the agent runs, **then** no mail is skipped or processed twice, and processing resumes when the service is back. | How I will know |
| AC-13 | **Given** no existing category fits, **when** the agent categorises, **then** it creates a new category label under the prefix, up to the maximum, and never creates more. | What I want |
| AC-14 | **Given** normal operation, **when** logs and errors are written, **then** mail bodies, addresses beyond what is needed, and the API key and tokens never appear in them or in URLs. | Must not do |

## Constraints from existing decisions

- Gmail through the REST API with scopes readonly, send and modify (ADR-0011); the agent only uses label changes and sending, never trash or delete calls.
- Agent and Telegram gateway are separate containers in `agents/` and `channels/` (ADR-0005); Kubernetes via Helm and Argo CD in production (ADR-0012).
- PostgreSQL for state (ADR-0007); Sentry and Grafana for operation (ADR-0013).
- The mailbox holds personal data. Mail text goes to the Anthropic API; this is accepted by Marco for his own mailbox and must be handled in the threat model (phase 2).
- `guardrail-gmail` does not exist in the kit's guardrail list and is not active in `CLAUDE.md`. It must be created with `guardrail-author` before building (phase 3b).

## Approaches considered

| Approach | Trade-off | Chosen |
|---|---|---|
| **A. Polling** the Gmail API every minute | Simple, works locally and on Kubernetes without a public address. Delay of at most a couple of minutes. | **Yes (Marco)** |
| B. Push through Gmail watch and Pub/Sub | Near-instant, but needs a public HTTPS endpoint, Google Cloud Pub/Sub and renewal every 7 days; larger attack surface. | No |

The fetching part is kept behind its own boundary so that B can replace A later without rewriting categorisation, alerts or replies.

## Open questions (not blockers for approval; for the next phases)

- Quiet hours: should Marco not be alerted at night?
- Can Marco name a different recipient than the sender when he replies?
- Phase 2 threat model: what the model sees (full body or a trimmed part), prompt injection through mail content, who may use the Telegram bot, and how the confirmation step cannot be skipped.
- Phase 3: Gmail OAuth for a single owner (ADR-0008 describes a web login that this feature does not need) and how the Telegram bot token and Anthropic API key are stored as secrets.
