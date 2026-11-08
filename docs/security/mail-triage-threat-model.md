---
feature: mail-triage
spec: docs/specs/mail-triage.md
intent: INT-001
status: approved
date: 2026-11-08
approver: Marco
---

# Threat model: mail-triage

## Scope

Feature `mail-triage` (spec `docs/specs/mail-triage.md`). Components:

- **Triage agent** (`agents/`): polls Gmail, calls the model, decides category and urgency, sends alerts, sends confirmed replies.
- **Telegram gateway** (`channels/`): the only channel to Marco.
- **PostgreSQL**: processed-mail state, pending alerts, drafts, reminders, encrypted Gmail refresh token.
- **External services**: Gmail API, Anthropic API, Telegram Bot API.
- **Infra**: containers on Docker Desktop (dev) and Kubernetes (prod, ADR-0012).

Out of scope: any web UI (none exists in this feature).

## Data classification

| Data | Class | GDPR | Where it lives / travels |
| --- | --- | --- | --- |
| Mail body, subject, sender and recipient addresses | Personal data, confidential (may contain special-category data, third parties' data) | Yes | Gmail → agent memory → Anthropic API; trimmed summary → Telegram |
| Mail summary and reason in an alert | Personal data, confidential | Yes | Agent → Telegram servers → Marco's device |
| Marco's reply text and the sent mail | Personal data, confidential | Yes | Telegram → agent → Gmail |
| Gmail refresh token | Secret | – | PostgreSQL, encrypted at rest; access token in memory only (ADR-0011) |
| Telegram bot token | Secret | – | Secret store; appears in Telegram API URLs |
| Anthropic API key | Secret | – | Secret store |
| Processing state (ids, labels, timers, decisions) | Internal; contains mail ids | Low | PostgreSQL |
| Audit records (what was alerted, confirmed, sent) | Internal; no bodies | Low | PostgreSQL |

## Diagram

Trust boundaries: (1) internet ↔ our cluster, (2) between our components, (3) mail content is **untrusted input** even though it arrives through an authenticated channel.

```text
 Sender (anyone) ──mail──► Gmail ◄──OAuth/REST── Triage agent ──► PostgreSQL
                                                     │  ▲
                              untrusted mail text ───┘  │ structured result only
                                                     ▼  │
                                              Anthropic API
                                                     │
                                    alert / confirm  ▼  ▲  Marco's choice, reply text
                                              Telegram gateway ◄──► Telegram ◄──► Marco
```

(An archify HTML diagram can be generated in phase 3 together with the architecture diagram.)

## Threats

L = likelihood, I = impact (L/M/H). Risk is the combination; "High" needs a mitigation, "Medium" a mitigation or an accepted risk.

| id | element | STRIDE | threat | L | I | mitigation | criterion | ASVS / OWASP |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-01 | Telegram gateway | S | Another person finds the bot and sends commands or confirms a draft as if they were Marco. | M | H | Only Marco's numeric Telegram user id and chat id are accepted (allow-list from configuration); all other updates are dropped without a reply. Gateway uses long polling so no public inbound endpoint exists. | SC-1 | ASVS V4 access control |
| T-02 | Incoming mail | S | Forged `From` or a misleading `Reply-To` makes the agent show or use a wrong address, so a reply reaches an attacker. | H | H | The reply goes to the `From` address only. If `Reply-To` differs the alert shows a warning and Marco must name it explicitly. The confirmation shows the exact recipient. Authentication results (SPF/DKIM/DMARC) are shown in the alert when present. | SC-2, SC-3 | ASVS V5 |
| T-03 | Model call | T | **Prompt injection**: mail text tells the model to send mail, delete, hide itself, mark itself non-urgent, or reveal other mail. | H | H | The model has no tools. It returns one structured object (category, urgent, reason, summary) that is validated against a schema; anything else is rejected. Sending, labelling and alerting are done by deterministic code. Mail text is passed as data, never merged into instructions. Low confidence or a schema failure means the mail is treated as needs-attention, not as ignorable. | SC-4, SC-5 | OWASP LLM01, LLM06; guardrail-llm |
| T-04 | Confirmation step | T | A draft is changed after Marco confirmed it, or a confirmation is replayed or applied to another draft. | M | H | The confirmation is bound to a draft id and a hash of recipient, subject and body. Only the matching, unexpired, unused confirmation sends; the sent text is the stored text. | SC-6 | ASVS V4, V13 |
| T-05 | Alert rendering | T | Mail text in the summary contains Telegram markup or links that look like buttons or hide the real target. | M | M | The alert is plain text or escaped; links are shown as plain addresses, never as masked links. Summary length is capped. | SC-7 | ASVS V5 |
| T-06 | Audit | R | Nobody can later tell what was sent, who confirmed it, or why a mail was judged urgent. | M | M | An audit record per alert, decision, confirmation and send: ids, timestamps, hashes, model decision and reason. No mail bodies. | SC-8 | ASVS V7 |
| T-07 | Anthropic API | I | Mail content (personal data of Marco and third parties) leaves our infrastructure. | H | M | Accepted by Marco (D8). Reduce: only subject, sender, body text trimmed to a maximum size; no attachments; no unrelated mails in one call; API key from secret store. See accepted risk A-1. | SC-9 | ASVS V8; OWASP LLM02 |
| T-08 | Telegram | I | Alerts (summary of personal mail) pass through Telegram's servers, which are not end-to-end encrypted for bots. | H | M | Accepted by Marco (D3). Reduce: a short summary only, never full body or attachments. See accepted risk A-2. | SC-7 | ASVS V8 |
| T-09 | Logs, errors, URLs | I | Mail text, tokens or the API key end up in logs, Sentry or traces; the Telegram bot token sits in request URLs and may be logged by an HTTP client. | H | H | Logging redacts bodies, tokens and URLs containing the bot token; Sentry events are scrubbed before sending; secrets never in code, images or Git. | SC-10 | ASVS V7, V14 |
| T-10 | PostgreSQL | I | Database or backup leak exposes the Gmail refresh token, which gives access to the whole mailbox. | L | H | Refresh token encrypted at rest with a key from the secret store, not in the database; access tokens in memory only; least-privilege database user. | SC-11 | ASVS V6, V8 |
| T-11 | Mail flood | D | A flood of mails exhausts model budget or floods Marco with alerts. | M | M | Hard daily model budget and a size cap per mail; maximum alerts per hour (excess batched into one summary alert); polling uses backoff. | SC-12 | OWASP LLM10 |
| T-12 | Poison mail | D | One mail always fails (too big, odd encoding) and blocks the queue or retries forever. | M | M | Processing is per mail with a retry limit; after the limit the mail stays in the inbox and Marco receives one error notice; the queue continues. | SC-13 | ASVS V7 |
| T-13 | Outages | D | Gmail, Anthropic or Telegram is down; mails are skipped, processed twice or alerts are lost. | M | M | Idempotent processing keyed on the Gmail message id; resume from the last processed point; a failed alert is retried. | SC-13 | – |
| T-14 | Gmail scope | E | `gmail.modify` also allows trashing and deleting. A bug or an injection could delete mail. | M | H | The Gmail client wrapper exposes only: read, add or remove labels, create a label, send. No trash, delete or spam call exists; a test fails if one is added. | SC-14 | ASVS V4; OWASP LLM06 |
| T-15 | Auto-reply loop | E | The agent replies to an automatic sender, a list, or its own sent mail, causing a loop or spam. | L | M | Replies are blocked for senders marked `Auto-Submitted`, `List-Id`, `Precedence: bulk` or `noreply`; sent mail is excluded from processing; sends are rate limited. | SC-15 | – |
| T-16 | Label creation | E | Runaway creation of labels (injection or model drift). | L | L | Maximum number of categories (spec: 15) and a fixed prefix; a name must pass a pattern check. | AC-13 | – |
| T-17 | Containers | E | A compromised agent container reaches other services or the cluster. | L | H | Non-root, read-only filesystem, no extra capabilities, network policy that allows only Gmail, Anthropic, Telegram and PostgreSQL; separate secrets per component (guardrail-kubernetes, guardrail-docker). | SC-16 | ASVS V14 |

## Security acceptance criteria

These are added to the spec as AC-15 to AC-30 and become tests in phase 5. They are written in Given/When/Then there.

| id | Short form |
| --- | --- |
| SC-1 | Telegram updates from any user or chat other than Marco's are ignored. |
| SC-2 | A reply goes to the `From` address; a differing `Reply-To` is flagged and never used silently. |
| SC-3 | The confirmation always shows the exact recipient, subject and body. |
| SC-4 | Model output that does not match the schema is rejected and the mail is treated as needs-attention. |
| SC-5 | Instructions inside mail text have no effect on categories, alerts, sending or deletion (tested with injection samples). |
| SC-6 | A confirmation only sends the draft it was issued for, once, within its validity. |
| SC-7 | Alert text is escaped, has a length cap, and contains no masked links. |
| SC-8 | Every alert, decision, confirmation and send writes an audit record without a mail body. |
| SC-9 | Only subject, sender and trimmed text go to the model; never attachments. |
| SC-10 | Bodies, tokens, the API key and URLs with the bot token never appear in logs or error reports. |
| SC-11 | The refresh token is stored encrypted, and the key is not in the database. |
| SC-12 | A daily model budget and an alerts-per-hour cap apply; excess is batched. |
| SC-13 | Each mail is processed at most once successfully; failures retry up to a limit and then stop with one notice. |
| SC-14 | The Gmail wrapper has no trash, delete or spam operation, and a test enforces it. |
| SC-15 | No reply is created for automatic or list senders or for the agent's own mail. |
| SC-16 | The agent runs as non-root with an egress allow-list. |

## Accepted risks (owner: Marco; each needs an ADR in phase 3)

| id | Risk | Why accepted |
| --- | --- | --- |
| A-1 | Mail text (including third parties' data) is sent to the Anthropic API. | Marco chose the Anthropic API for his own personal mailbox (D8). Reduced by trimming and by no attachments (SC-9). |
| A-2 | Short summaries of mail are delivered through Telegram's servers. | Marco chose Telegram as the only interface (D3). Reduced by short summaries only (SC-7). |

## Spec delta from this model

- C4 of the spec changes: the reply goes to the `From` address; `Reply-To` is only used when Marco names it (T-02).
- AC-15 to AC-30 are added from SC-1 to SC-16.

## Decisions from the open questions (Marco, 2026-11-08)

1. Hidden mail: a daily overview of mails that were not alerted is sent (spec D10, AC-31).
2. Telegram transport: long polling (spec D11).
3. Anthropic data handling: Marco checks the retention setting of his API account (zero retention if offered) before the first run; recorded in the ADR for A-1 in phase 3.
4. Attachments are never read or sent to the model (spec D12, AC-23).
5. Quiet hours apply; alerts inside them are held and sent together afterwards (spec D13, AC-32).
