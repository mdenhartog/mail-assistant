# Architecture

This page is the baseline of the system as it is built (model: [model.json](model.json)). The component table is
generated from the model, see [Components](#components).

## Context

Several people can start this agent. Each is a user with their own mailbox who signs in before using it. Today the
system serves one user; INT-004 (confirmed) plans a second Google account and one agent per mailbox, so single-tenant is
a choice of the current build, not a principle; see drift item 1.

- A user reads alerts and answers in Telegram from anywhere.
- A user changes settings on the web page, only on the local network (ADR-0037).

All calls to outside systems go outward:

- The mail-triage agent calls Gmail, Google OAuth, Anthropic and Telegram. It polls; there is no inbound endpoint (ADR-0019).
- The api calls an SMTP server to send the sign-in code.
- The only inbound traffic is browser to Traefik to web and api, on a private address.

The agent and the api never call each other and never import each other. They meet only in PostgreSQL schemas:
`settings` (ADR-0023, ADR-0025) and `web_auth.web_lock` plus `security_event` (ADR-0033, ADR-0039).

## Quality attributes

| Attribute | Target | Source |
|---|---|---|
| Triage latency | Mail labelled within 5 minutes of arrival; poll every minute | spec mail-triage (proposed, no ADR) |
| Web-change notice | Within one agent run interval | ADR-0033 |
| Agent independence | The agent keeps working when the api is down, with the last values or defaults | ADR-0023 |
| Replicas | Agent: 1, guarded by a database lock. Api: exactly 1, in-process rate limits | ADR-0019, ADR-0034 |
| Exposure | No public inbound; web only on the local network | ADR-0019, ADR-0037 |
| Transport | TLS 1.2 minimum, HSTS without includeSubDomains, 8 KB body limit, Traefik | ADR-0040, ADR-0034 |
| Least privilege | One login role per runtime, per-table grants, server-derived audit actor | ADR-0025, ADR-0030 |
| Sign-in abuse | 6-digit code, 10 minutes, 5 tries, cooldown, hourly cap, decoys, web lock after repeated wrong codes | ADR-0036, ADR-0038, ADR-0039 |
| Retention | Alert content 30 days | ADR-0020 |
| Retention | Security events 90 days, settings audit 1 year | spec web-settings (proposed, no ADR) |
| Secrets | Sealed Secrets in the cluster, `.env` locally | ADR-0029, ADR-0017 |
| Model budget | Daily budget; the catch-up keeps a reserve | ADR-0021 |
| Data disclosure | Mail text to Anthropic and summaries to Telegram are accepted | ADR-0018 |
| Certificate expiry | Alert 14 days ahead | ADR-0037 |
| Observability | Sentry and Grafana | ADR-0013 (not implemented, see drift) |
| Test quality | Mutation score of 85 % or more, nightly | ADR-0030 |
| Backup, RPO, RTO | Not defined | proposed, no ADR |

## Data and trust boundaries

| Store | Owner (writes) | Classification | Note |
|---|---|---|---|
| `public` schema | mail-triage only | Confidential | Mail metadata and summaries, encrypted Gmail refresh token. The api role has no grant here (ADR-0025). |
| `settings` schema | mail-triage and api, through the shared contract | Confidential | Time zone and quiet hours show the user's routine. Channel and actor of a change come from `session_user` by trigger (ADR-0030). |
| `web_auth` schema | api; the agent writes `web_lock` and reads four columns of `security_event` | Confidential | Hashed codes, session ids, client hashes. |

Trust boundaries: browser to Traefik, pods to PostgreSQL, the internet APIs (Gmail and OAuth, Anthropic, Telegram) and
SMTP. Also untrusted: mail senders (they can inject prompts and markup), model output, other devices on the local
network, and the seam between agent and api inside PostgreSQL. The migrate job (owner role) is the only holder of DDL rights.

## Placement guide

| Responsibility | Component |
|---|---|
| Mail reading, judging, labelling, sending | `mail-triage` adapters and use cases |
| Any Telegram interaction | `mail-triage` (ADR-0019) |
| Settings validation and time rules | `schedule-policy` |
| Browser-facing authentication and settings HTTP | `api` |
| User interface | `web`, styled only through `tokens` |
| DDL and grants of any schema | the `mail-triage` migrate chain (ADR-0025) |
| Web read of agent-produced data (decisions, reasoning), INT-006 | Not decided: leading option is an append-only schema written by the agent with a read-only grant for the api; see drift item 2 |
| Agent behaviour toggles | `settings` schema, through `schedule-policy` |
| Runtime and infrastructure configuration | `platform` |
| A new outside system | An adapter in the component that uses it; a new component only when a second consumer appears (ADR-0019) |

## Dependency rules

- `web` talks only to the `api`, over HTTP and the OpenAPI types. It never touches the database.
- `api` and `mail-triage` never import each other. Their only shared code is `schedule-policy`.
- Shared packages import no component.
- A new table that both runtimes touch needs an ADR, a grant test and a contract test.
- Calls to an external system go only through an adapter in the owning component.
- The checker sees imports only. Dependencies on datastores and external systems are documented, not enforced.

## Diagram

The context and container diagram is [system-architecture.html](system-architecture.html) (source:
`system-architecture.json`). The agent's own ports and adapters are in
[mail-triage-architecture.html](mail-triage-architecture.html).

## Drift found at the baseline

| # | Finding | Severity | Proposed action |
|---|---|---|---|
| 1 | The baseline is single-tenant, but INT-004 plans several mailboxes. Whether agent tables get a `mailbox_id` must be settled before INT-006 designs its log table | Blocker for INT-006 | Decision-gate at the design of INT-004 or INT-006 |
| 2 | INT-006 wants bot decisions in the web app, but ADR-0025 gives the api no access to mail content. Mail text is attacker-controlled, so it also risks stored XSS in the browser. Anyone with access to the mailbox can sign in (R-1 of the web-settings threat model) | Blocker for INT-006 | New ADR that supersedes the relevant part of ADR-0018, an R-1 re-review, a read-only view without mail bodies, output encoding, and a grant test that `web_settings_runtime` cannot select from `public.mail_item` |
| 3 | `web_auth` belongs to the api, but its DDL and grants live in the mail-triage chain and image. No ADR records this | High | Decision-gate: record "one migrator" as intended (the migrate job is not a separate component, it shares the agent's code), or give the api its own chain |
| 4 | The sign-in code mail goes to the user's configured address. If that is the mailbox the agent reads, the live code could reach Anthropic, Telegram and `public`. No exclusion rule was found; not yet verified end to end | High, to verify | Verify by test; add a skip rule if confirmed |
| 5 | The scaffolds `assistant`, `chat-gateway` and `tools` are unused, but they are the start of the wanted chat with the agent in Telegram and later WhatsApp. They conflict with ADR-0017 (Bedrock instead of the Anthropic API), ADR-0019 and ADR-0037 (no inbound traffic; WhatsApp needs a public webhook), and a second client on the Telegram bot would break the long polling of `mail-triage`. They are still built and scanned in CI | Medium | Keep. Decide in the design of the chat intent: who owns the Telegram bot, the model provider, and how WhatsApp is reached; then rebuild or remove them |
| 6 | No backup target for PostgreSQL. Settings history and the INT-006 log cannot be rebuilt from Gmail | Medium | Small ADR, for example nightly dump, RPO 24 hours |
| 7 | ADR-0013 names Sentry and Grafana; neither is wired. A single user needs to know when the bot stops | Medium | Supersede with a Telegram alert when no poll succeeded for 15 minutes |
| 8 | ADR-0011 names Google Calendar; no code uses it | Low | Amend the ADR to "planned" or remove |
| 9 | ADR-0005 names `deploy/charts/component`, but the migrate job runs in the worker chart | Low | Correct the ADR |

## Components of mail-triage

| Part | Where | Responsibility |
|---|---|---|
| Core | `agents/mail-triage/app/core` | Pure logic without I/O: urgency, alert states, the text of alerts and of the settings dialogue |
| Use cases | `agents/mail-triage/app/usecases` | Triage, alert delivery, overview, snooze, reply, the settings dialogue and its confirmation |
| Adapters | `agents/mail-triage/app/adapters`, `app/db` | One adapter per outside system: Gmail, Anthropic, Telegram, PostgreSQL |
| `schedule_policy` | `packages/schedule-policy` | Shared Python package: the `TimePolicy` model, the validation of a whole row, the typed-time parser and the place list. The agent uses it now; the later web backend uses the same code (ADR-0025, ADR-0028) |
| Migrate job | `python -m app migrate` | One-shot job run before the agent: migrations, runtime role and grants (ADR-0025, ADR-0030) |

## Data and where it lives

PostgreSQL holds everything. The agent's Alembic chain is the only migrator.

| Data | Place | Note |
|---|---|---|
| Mail, alerts, drafts, the Gmail token, audit and overview log | schema `public` | Append-only audit tables; see the grants in `app/db/grants.sql` |
| The four settings | `settings.schedule` (one row with a `version`) | Every write replaces the whole row with a version check (ADR-0023, ADR-0025) |
| History of settings changes | `settings.settings_change` | Written by a database trigger only: time, channel, actor, old and new values |
| The pending Telegram dialogue | `conversation` (one row) | Snooze, reply and settings questions share it (ADR-0026) |
| Update cursor | `poll_state.telegram_update_id` | The last handled Telegram update, so a restart does not replay it |

## Start-up and trust boundaries

1. The migrate job connects as the database owner role, takes an advisory lock, migrates, sets up the login role
   `mail_triage_runtime` and applies its grants. Only this job holds the owner credentials.
2. The agent connects as `mail_triage_runtime`. It owns nothing, cannot run DDL, and at start only checks that the
   schema is at the expected head (exit 5 when not).
3. The database derives the channel and the actor of a settings change from the login role, so the agent cannot
   claim another channel (ADR-0030).
4. In Kubernetes the migrate job is a PreSync hook of the `worker` chart, and the secrets are sealed
   (ADR-0029); see [the worker chart](../../deploy/charts/worker/README.md).

## Decisions

| ADR | Subject |
|---|---|
| [ADR-0023](../memory/decisions/ADR-0023-settings-shared-table.md) | Settings in a shared PostgreSQL table |
| [ADR-0025](../memory/decisions/ADR-0025-settings-contract.md) | Settings contract, schema, roles and shared package |
| [ADR-0026](../memory/decisions/ADR-0026-single-conversation-state.md) | One conversation state for all Telegram dialogues |
| [ADR-0027](../memory/decisions/ADR-0027-wall-clock-resolution.md) | Wall-clock rules for gaps and repeated hours |
| [ADR-0028](../memory/decisions/ADR-0028-place-list.md) | The place list for time-zone lookup |
| [ADR-0029](../memory/decisions/ADR-0029-secrets-sealed-secrets.md) | Cluster secrets with Sealed Secrets |
| [ADR-0030](../memory/decisions/ADR-0030-runtime-role-hardening.md) | Runtime role hardening |

## Components

<!-- architecture:components:start -->

Generated from `docs/architecture/model.json` by `node scripts/architecture.mjs render`; edit the model, not this table.

| Component | Kind | Responsibility | Owns | May depend on | Code |
|---|---|---|---|---|---|
| Mail-triage agent (`mail-triage`) | agent | Polls Gmail, judges each new mail with the model, labels it and runs every Telegram dialogue with the user (alerts, snooze, reply, settings, web-change notices, web lock); its migrate job is the only migrator of the database. | public schema: mail items, alerts, drafts, audit and overview log, conversation state, poll state, web_notice_token (full rights), encrypted Gmail token; Alembic chain and grants for all schemas (public, settings, web_auth), run by its migrate job with the owner role (ADR-0025, ADR-0030); web_auth: select, insert, update and delete on web_lock; select on four columns of security_event (ADR-0033, ADR-0039) | `schedule-policy`, `postgres`, `gmail`, `google-oauth`, `anthropic`, `telegram` | `agents/mail-triage` |
| Web settings API (`api`) | backend | Serves the settings API to the web page: username plus e-mailed one-time-code sign-in, sessions, CSRF, rate limits and versioned reads and writes of the shared settings row. | web_auth sessions, login requests and security events (data; the DDL lives in the mail-triage chain); co-writer of settings.schedule through the shared contract (ADR-0023, ADR-0025); OpenAPI contract docs/api/openapi.json | `schedule-policy`, `postgres`, `smtp` | `backend` |
| Web app (`web`) | frontend | Responsive settings page in the browser: sign-in with username and code, and viewing and changing the settings, only through the api's OpenAPI contract. | unsaved form draft in the browser tab | `api`, `tokens` | `apps/web` |
| schedule-policy (`schedule-policy`) | shared | Pure Python rules for the settings contract: the TimePolicy model, whole-row validation, typed-time parsing and the place list for time-zone lookup, used by both mail-triage and the api. | settings validation rules and contract cases; place list (ADR-0028) | — | `packages/schedule-policy` |
| Design tokens (`tokens`) | shared | Single source of the Pebble design tokens and fonts, generated into CSS for the web app (ADR-0035). | token source and the generated CSS | — | `packages/tokens` |
| Deployment (`platform`) | platform | Runs the system: Helm charts, environment values, Argo CD objects, Traefik ingress, network policies, sealed-secret references and the local and prod-like stack support files. | Kubernetes manifests, values per environment, ingress and TLS settings | — | `deploy` |
| assistant (unused scaffold) (`assistant`) | agent | Unused scaffold of a Strands chat agent on Bedrock AgentCore, kept as the start of the wanted chat with the agent; it conflicts with ADR-0017 and must be rebuilt for the Anthropic API when that feature is designed. | — | `tools`, `aws-bedrock` | `agents/assistant` |
| chat-gateway (unused scaffold) (`chat-gateway`) | channel | Unused scaffold of a stateless Telegram and WhatsApp webhook relay to an agent, kept as the start of the wanted chat; it conflicts with ADR-0019 and ADR-0037 and must be re-decided when that feature is designed. | — | `assistant`, `telegram`, `whatsapp`, `aws-bedrock` | `channels/chat-gateway` |
| tools (unused scaffold) (`tools`) | mcp-server | Unused scaffold of an MCP tool server, kept as the start of the wanted chat with the agent; no feature uses it yet. | — | — | `mcp-servers/tools` |
| PostgreSQL (`postgres`) | datastore | The one relational database (ADR-0007), split in schemas with one login role per runtime and least-privilege grants (ADR-0025, ADR-0030). | public: mail-triage state, capped mail content (30 days, ADR-0020), encrypted Gmail refresh token, audit (confidential); settings: schedule (shared contract) and settings_change (append-only, trigger-written); time zone and quiet hours reveal the user's routine (confidential); web_auth: sessions, login requests with hashed codes, security events, web_lock (confidential) | — | — |
| Gmail API (`gmail`) | external | The user's mailbox: mail-triage lists, labels and (after confirmation) sends mail (ADR-0011). | — | — | — |
| Google OAuth 2.0 (`google-oauth`) | external | One-time consent and token refresh for the Gmail scopes of mail-triage. | — | — | — |
| Anthropic API (`anthropic`) | external | Judges each mail (category, urgency, summary) with a JSON-schema result (ADR-0017; accepted risk in ADR-0018). | — | — | — |
| Telegram Bot API (`telegram`) | external | The user's channel for alerts, buttons, dialogues and notices; long polling, no inbound endpoint (ADR-0019; accepted risk in ADR-0018). | — | — | — |
| SMTP server (`smtp`) | external | Delivers the sign-in code mail from a send-only account over STARTTLS (ADR-0036); smtp4dev in local stacks (INT-005), the production server is not decided yet. | — | — | — |
| Amazon Bedrock / AgentCore (`aws-bedrock`) | external | Model and runtime provider referenced only by the unused scaffolds; rejected for this project by ADR-0017. | — | — | — |
| WhatsApp Cloud API (`whatsapp`) | external | Referenced only by the unused chat-gateway scaffold; no ADR chooses it. | — | — | — |

<!-- architecture:components:end -->
