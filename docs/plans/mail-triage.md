---
feature: mail-triage
spec: docs/specs/mail-triage.md
design: docs/design/mail-triage-design.md
threat-model: docs/security/mail-triage-threat-model.md
intent: INT-001
status: draft
date: 2026-11-08
---

# Plan: mail-triage

All code lives in the new component `agents/mail-triage` (ADR-0019), Python, no UI. Each unit gets its own git worktree and branch (`feat/mail-triage-<nn>-<slug>`), is built test-first (a failing test is shown before any implementation) and is merged by a PR that Marco approves. Test names follow `test_given_x_when_y_then_z`. Ids AC-n refer to the spec.

Common guardrails for every unit: `guardrail-python`, `guardrail-pytest`. Others are listed per unit.

## Order and parallelism

```text
U-01 skeleton ──┬─ U-02 alert state machine ─┐
                ├─ U-03 time policy ──────────┤
                ├─ U-04 judgement schema ─────┤
                ├─ U-05 Gmail read/label ─────┤
                ├─ U-06 Gmail send ───────────┼─► U-10 pipeline ─► U-13 alert delivery ─┐
                ├─ U-07 token store ──────────┤                   U-14 reply flow ──────┤
                ├─ U-08 model adapter ────────┤                   U-15 snooze/close ─────┼─► U-19 end-to-end check
                ├─ U-09 persistence ──────────┤                   U-16 daily overview ───┤
                ├─ U-11 telegram intake ──────┘                   U-12 alert text ───────┤
                ├─ U-17 log redaction ─────────────────────────────────────────────────────┤
                └─ U-18 container & deploy ───────────────────────────────────────────────┘
```

Parallel groups: (U-02, U-03, U-04, U-05, U-06, U-07, U-08, U-09, U-11, U-17, U-18) after U-01; (U-12, U-13, U-14, U-15, U-16) after their dependencies. U-10 needs the group above it. U-19 is last.

## Units

### U-mail-triage-01: Component skeleton and configuration

- Layer: backend (scaffold from `/sdlc:component agent mail-triage`, then adapted)
- Contract: `Settings` (pydantic-settings) loaded from environment; fails at startup when a required secret or id is missing; component registered in `.sdlc/components.json`.
- Files: `agents/mail-triage/pyproject.toml`, `app/settings.py`, `app/main.py`, `tests/test_settings.py`, `.sdlc/components.json`
- Depends on: —
- Parallel: no
- Guardrails: guardrail-pydantic, guardrail-docker, guardrail-llm
- Criteria:
  1. Given all required values, When settings load, Then they are typed and defaults match spec C1; quiet hours, overview time and time zone are not settings (they are constants, spec C7) (happy).
  2. Given a missing `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN` or allowed user id, When the app starts, Then it refuses to start with a message that names the missing key but not any value (error, security).
  3. Given settings are printed or logged, When secrets are present, Then they appear masked (security).
  4. Given model ids, When configured, Then no model id literal exists in code (edge).

### U-mail-triage-02: Alert state machine

- Layer: backend (pure core)
- Contract: `transition(state, event) -> state` for states `held, open, snoozed, drafting, confirming, closed` and events `quiet_end, remind_later(due), close, start_draft, show_draft, cancel_draft, sent, due`; illegal transitions raise `InvalidTransition`.
- Files: `app/core/alert_state.py`, `tests/core/test_alert_state.py`
- Depends on: U-01
- Parallel: yes
- Guardrails: —
- Criteria:
  1. Given an `open` alert, When `close` happens, Then it is `closed` and never returns to `open` (happy; AC-10).
  2. Given an `open` alert with no event, When time passes, Then it stays `open` and no new alert is requested (edge; AC-5).
  3. Given `open`, When `remind_later` with a due time, Then `snoozed`; When `due`, Then `open` again exactly once (happy; AC-9).
  4. Given `confirming`, When `cancel_draft`, Then `open` (happy; AC-8).
  5. Given `confirming`, When `sent`, Then `closed` (happy; AC-7).
  6. Given `closed`, When any event except a new mail arrives, Then `InvalidTransition` (error).

### U-mail-triage-03: Time policy (quiet hours, snooze, overview time)

- Layer: backend (pure core)
- Contract: `in_quiet_hours(now)`, `next_quiet_end(now)`, `snooze_due(now, hours | "tomorrow")`, `next_overview(now)`; the values (23:00-07:00, 18:00, 09:00, Europe/Amsterdam) are module constants (spec C7), not configuration.
- Files: `app/core/time_policy.py`, `tests/core/test_time_policy.py`
- Depends on: U-01
- Parallel: yes
- Guardrails: —
- Criteria:
  1. Given 23:30 local, When asked, Then it is quiet hours and the end is 07:00 next day (happy; AC-32).
  2. Given 07:00 exactly, When asked, Then not quiet (edge).
  3. Given a daylight-saving change night, When computing the end of quiet hours, Then it is 07:00 local time (edge).
  4. Given "tomorrow" at 15:00, When snoozing, Then due is the next day at 09:00 local (happy; AC-9).
  5. Given a number of hours that is zero, negative or above 168, When snoozing, Then it is rejected (error).
  6. Given 17:59 and 18:00, When computing the next overview, Then 18:00 today and 18:00 tomorrow (edge; AC-31).

### U-mail-triage-04: Judgement schema and category policy

- Layer: backend (pure core)
- Contract: `Judgement` model (`category`, `urgent`, `reason`, `summary`, `confidence`) with strict validation; `resolve(judgement, existing_labels) -> Decision` (uses a label, creates a label, or needs-attention).
- Files: `app/core/judgement.py`, `tests/core/test_judgement.py`
- Depends on: U-01
- Parallel: yes
- Guardrails: guardrail-pydantic, guardrail-llm
- Criteria:
  1. Given valid model output, When parsed, Then a `Judgement` is returned (happy).
  2. Given extra fields, wrong types or a missing field, When parsed, Then it is rejected and the decision is needs-attention (error, security; AC-18).
  3. Given confidence below the threshold, When resolved, Then needs-attention (edge; AC-18).
  4. Given a category that exists, When resolved, Then that label is used (happy; AC-1).
  5. Given a new category name that matches `Assistant/<name>` and fewer than 15 exist, When resolved, Then it is created (happy; AC-13).
  6. Given 15 categories exist or the name breaks the pattern (path characters, over-long), When resolved, Then the closest existing category or `Assistant/Other` is used and no label is created (security; AC-13).
  7. Given `reason` or `summary` longer than the cap, When parsed, Then it is cut at the cap (edge; AC-21).

### U-mail-triage-05: Gmail read and label operations

- Layer: backend (adapter)
- Contract: `GmailReader` with `list_new(history_id)`, `fetch(message_id)`, `ensure_label(name)`, `file(message_id, label)`; no other methods.
- Files: `app/adapters/gmail_read.py`, `tests/adapters/test_gmail_read.py`
- Depends on: U-01
- Parallel: yes
- Guardrails: guardrail-gmail, guardrail-api-client, guardrail-oauth2-oidc
- Criteria:
  1. Given two pages of history, When `list_new` runs, Then all new inbox mails are returned (happy; guardrail pagination).
  2. Given the agent's own sent mail, When listing, Then it is excluded (security; AC-29).
  3. Given a mail with attachments, When `fetch` runs, Then only headers and the text part are fetched, never an attachment (security; AC-23).
  4. Given a category label, When `file` runs, Then exactly that label is added and `INBOX` is removed and nothing else changes (happy; AC-1).
  5. Given the module source, When scanned, Then it references no trash, delete or spam method (security; AC-2, AC-28).
  6. Given HTTP 429, When a call runs, Then it retries with backoff and then succeeds (error; AC-12).
  7. Given an expired access token, When a call runs, Then it refreshes and continues (edge).

### U-mail-triage-06: Gmail send reply

- Layer: backend (adapter)
- Contract: `GmailSender.send_reply(draft: ConfirmedDraft) -> sent_message_id`
- Files: `app/adapters/gmail_send.py`, `tests/adapters/test_gmail_send.py`
- Depends on: U-01
- Parallel: yes
- Guardrails: guardrail-gmail, guardrail-api-client
- Criteria:
  1. Given a confirmed draft, When sent, Then the mail goes in the same thread with correct `In-Reply-To` and `References` (happy; AC-7).
  2. Given a mail with a `Reply-To` different from `From`, When replying, Then the recipient is `From` unless the draft names another address (security; AC-16).
  3. Given the original has `Auto-Submitted`, `List-Id`, `Precedence: bulk` or a `noreply` sender, When a reply is requested, Then nothing is sent and the caller receives `NotRepliable` (security; AC-29).
  4. Given the authenticated address differs from the requested sender, When sending, Then it refuses (security; guardrail rule).
  5. Given a send call that fails after a timeout, When retried, Then no duplicate is sent (edge; idempotency key on the draft).
  6. Given the module source, When scanned, Then it references no trash, delete or spam method (security; AC-28).

### U-mail-triage-07: Token store and one-time consent

- Layer: backend (adapter and command-line tool)
- Contract: `TokenStore.save(refresh_token)`, `.load()`; `python -m app.consent` runs the OAuth consent for the owner (PKCE) and stores the result.
- Files: `app/adapters/token_store.py`, `app/consent.py`, `tests/adapters/test_token_store.py`
- Depends on: U-01, U-09
- Parallel: no (needs the table from U-09)
- Guardrails: guardrail-oauth2-oidc, guardrail-sqlalchemy-alembic
- Criteria:
  1. Given a refresh token, When saved, Then the stored value is encrypted and decrypts to the original (happy; AC-25).
  2. Given the database content, When read directly, Then the plain token is not present and the key is not in the database (security; AC-25).
  3. Given a wrong or missing key, When loading, Then it fails closed with no partial value (error).
  4. Given the consent flow, When it runs, Then it uses PKCE and `state` and asks only for the three scopes in ADR-0011 (security).
  5. Given consent output, When logged, Then no token or authorisation code appears (security; AC-24).

### U-mail-triage-08: Model adapter (Anthropic)

- Layer: backend (adapter)
- Contract: `Judge.judge(mail: TrimmedMail) -> Judgement | NeedsAttention`; internal escalation from the small to the large model.
- Files: `app/adapters/judge_anthropic.py`, `tests/adapters/test_judge_anthropic.py`, `tests/fixtures/injection/*.txt`
- Depends on: U-01, U-04
- Parallel: yes
- Guardrails: guardrail-llm, guardrail-api-client
- Criteria:
  1. Given a mail, When judged, Then the request contains only subject, sender and trimmed text, never attachments (security; AC-23).
  2. Given a body above the size cap, When trimmed, Then it is cut at the cap and the cut is marked (edge).
  3. Given mail text with instructions ("send this to…", "delete all mail", "mark as not urgent", "reveal other mail"), When judged with a scripted model, Then the result is still only a `Judgement` and the instructions have no effect on the call (security; AC-19).
  4. Given the model answers outside the schema, When judged, Then `NeedsAttention` (error; AC-18).
  5. Given low confidence from the small model, When judged, Then the large model is asked once and its result is used (happy; ADR-0014).
  6. Given the daily budget is used up, When a mail arrives, Then no model call is made and the result is `NeedsAttention` with reason `budget` (edge; AC-26).
  7. Given an API error or timeout, When judged, Then it retries within limits and then raises a retryable error (error; AC-12).
  8. Given the request is logged for debugging, When written, Then the mail text and the key are not in it (security; AC-24).

### U-mail-triage-09: Persistence

- Layer: backend (adapter)
- Contract: SQLAlchemy models and Alembic migration for `mail_item`, `alert`, `draft`, `audit_log`, `oauth_token`, `poll_state`; repositories; `try_claim(message_id)`; single-replica lock.
- Files: `app/db/models.py`, `app/db/repos.py`, `migrations/versions/0001_initial.py`, `tests/db/*`
- Depends on: U-01
- Parallel: yes
- Guardrails: guardrail-sqlalchemy-alembic, guardrail-pytest
- Criteria:
  1. Given the migration, When upgraded and downgraded, Then both succeed and the schema matches the models (happy).
  2. Given the same Gmail message id twice, When `try_claim` runs, Then only the first succeeds (edge; AC-12).
  3. Given two processes, When both try to take the lock, Then only one holds it (edge).
  4. Given an audit entry, When written, Then it stores ids, hashes and the decision, and the schema has no column for a mail body (security; AC-22).
  5. Given a draft, When stored, Then it has an expiry, a hash and a used flag, and a used draft cannot be reused (security; AC-20).
  6. Given the application database user, When it connects, Then it has only the rights it needs (security).

### U-mail-triage-10: Triage pipeline

- Layer: backend (use case)
- Contract: `run_once()`: list, claim, judge, file, create alert state; per-mail retry limit.
- Files: `app/usecases/triage.py`, `tests/usecases/test_triage.py`
- Depends on: U-02, U-03, U-04, U-05, U-08, U-09
- Parallel: no
- Guardrails: guardrail-python
- Criteria:
  1. Given a new non-urgent mail, When run, Then it is filed under one category, no alert is created and nothing is deleted (happy; AC-1, AC-2, AC-4).
  2. Given a new urgent mail outside quiet hours, When run, Then the alert state is `open` (happy; AC-3).
  3. Given a new urgent mail inside quiet hours, When run, Then it is filed at once and the alert is `held` (edge; AC-32).
  4. Given the same mail seen twice, When run twice, Then it is processed once (edge; AC-12).
  5. Given Gmail or the model is down, When run, Then no mail is lost or doubled and the next run resumes (error; AC-12).
  6. Given a mail that fails the retry limit, When run, Then the others continue and one error notice is requested (error; AC-27).
  7. Given a daily budget or alerts-per-hour cap, When exceeded, Then mails are still filed (edge; AC-26).

### U-mail-triage-11: Telegram intake (long polling)

- Layer: backend (adapter)
- Contract: `TelegramInbox` yields `Command` objects (button press, reply text) from updates; drops everything else.
- Files: `app/adapters/telegram_inbox.py`, `tests/adapters/test_telegram_inbox.py`
- Depends on: U-01
- Parallel: yes
- Guardrails: guardrail-telegram
- Criteria:
  1. Given an update from Marco's user and chat id, When received, Then a `Command` is produced (happy).
  2. Given an update from any other user or chat, When received, Then it is dropped without a reply and without effect (security; AC-11, AC-15).
  3. Given an update with an unknown shape (edited message, channel post, group), When received, Then it is dropped (security).
  4. Given a long-polling failure, When it occurs, Then it retries with backoff and keeps the offset so no update is lost or repeated (error).
  5. Given the bot token, When a request or error is logged, Then the URL is redacted (security; AC-24).

### U-mail-triage-12: Alert text

- Layer: backend (pure core)
- Contract: `build_alert(mail_meta, judgement, auth_results) -> AlertMessage` (text and the three buttons) and `build_digest(...)`.
- Files: `app/core/alert_text.py`, `tests/core/test_alert_text.py`
- Depends on: U-04
- Parallel: yes (after U-04)
- Guardrails: guardrail-telegram
- Criteria:
  1. Given a judgement, When built, Then the text has sender, subject, summary, reason and exactly the three buttons (happy; AC-3).
  2. Given text with Telegram markup or link syntax, When built, Then it is escaped and links are plain text (security; AC-21).
  3. Given a very long subject or summary, When built, Then it is cut at the cap (edge; AC-21).
  4. Given `Reply-To` differs from `From`, When built, Then a warning line is shown (security; AC-16).
  5. Given SPF, DKIM or DMARC failed, When built, Then a visible warning line is added (security).
  6. Given an attachment is present, When built, Then it says "has an attachment" and shows nothing of its content (edge; AC-23).

### U-mail-triage-13: Alert delivery

- Layer: backend (use case)
- Contract: `deliver_open_alerts()`: send each `open` alert once, honour the hourly cap, send held alerts after quiet hours.
- Files: `app/usecases/deliver_alerts.py`, `tests/usecases/test_deliver_alerts.py`
- Depends on: U-02, U-03, U-09, U-11, U-12
- Parallel: no
- Guardrails: guardrail-telegram
- Criteria:
  1. Given an `open` alert, When delivered, Then exactly one Telegram message is sent and its message id is stored (happy; AC-3).
  2. Given the same alert on the next run, When delivered, Then nothing is sent (edge; AC-5).
  3. Given held alerts and quiet hours end, When delivered, Then they go out together in one batch (happy; AC-32).
  4. Given more alerts than the hourly cap, When delivered, Then the excess is batched into one summary alert (edge; AC-26).
  5. Given Telegram fails, When delivering, Then the alert stays `open` and is retried without duplicate delivery (error; AC-12).
  6. Given each delivery, When done, Then an audit record is written without a body (security; AC-22).

### U-mail-triage-14: Reply flow with confirmation

- Layer: backend (use case)
- Contract: `start_reply(alert_id, text)`, `confirm(draft_id, token)`, `cancel(draft_id)`.
- Files: `app/usecases/reply.py`, `tests/usecases/test_reply.py`
- Depends on: U-02, U-06, U-09, U-11
- Parallel: no
- Guardrails: guardrail-telegram, guardrail-gmail
- Criteria:
  1. Given Marco's reply text, When `start_reply` runs, Then a draft is stored and shown with recipient, subject, body and Send, Edit, Cancel, and nothing is sent (happy; AC-6, AC-17).
  2. Given the shown draft, When Marco confirms, Then the exact stored text is sent once to the `From` address in the thread and the alert is `closed` (happy; AC-7).
  3. Given Cancel, When pressed, Then nothing is sent and the alert returns to `open` (happy; AC-8).
  4. Given Edit, When pressed and new text arrives, Then a new draft replaces the old one and the old confirmation no longer works (security; AC-20).
  5. Given a confirmation that was already used, expired or issued for another draft, When pressed, Then nothing is sent (security; AC-20).
  6. Given the draft hash no longer matches the stored text, When confirming, Then nothing is sent (security; AC-20).
  7. Given an automatic or list sender, When a reply is started, Then Marco is told it cannot be replied to and nothing is created (security; AC-29).
  8. Given each step, When done, Then an audit record is written without a body (security; AC-22).

### U-mail-triage-15: Snooze and close commands

- Layer: backend (use case)
- Contract: `snooze(alert_id, hours | "tomorrow")`, `close(alert_id)`, `release_due()`.
- Files: `app/usecases/snooze.py`, `tests/usecases/test_snooze.py`
- Depends on: U-02, U-03, U-09, U-11
- Parallel: yes (after those)
- Guardrails: guardrail-telegram
- Criteria:
  1. Given an alert, When Marco chooses "remind me later" and sends "3", Then the alert is `snoozed` with due now + 3 h and no alert is sent before then (happy; AC-9).
  2. Given "tomorrow", When chosen, Then the due time follows U-03 (happy; AC-9).
  3. Given the due time passes, When `release_due` runs, Then exactly one new alert is sent and the alert is `open` (happy; AC-9).
  4. Given invalid input for the hours, When sent, Then Marco is asked again and the state is unchanged (error).
  5. Given "no more reminders", When chosen, Then the alert is `closed` and the mail is never alerted again but keeps its category (happy; AC-10).
  6. Given a due time inside quiet hours, When released, Then the alert is `held` until quiet hours end (edge; AC-32).

### U-mail-triage-16: Daily overview

- Layer: backend (use case)
- Contract: `send_overview()` at the configured time.
- Files: `app/usecases/overview.py`, `tests/usecases/test_overview.py`
- Depends on: U-03, U-09, U-11, U-12
- Parallel: yes (after those)
- Guardrails: guardrail-telegram
- Criteria:
  1. Given mails filed today without alert, When the overview time arrives, Then one message gives counts per category and lists the mails with low confidence (happy; AC-31).
  2. Given nothing was filed, When the time arrives, Then no message is sent (edge; AC-31).
  3. Given the overview was already sent today, When run again, Then nothing is sent (edge).
  4. Given the overview time were to fall inside quiet hours, When it arrives, Then it is sent when quiet hours end (edge; guards a future change, see INT-002).

### U-mail-triage-17: Log and error-report redaction

- Layer: backend (cross-cutting)
- Contract: logging filter and Sentry `before_send` that remove mail text, tokens, the API key and URLs with the bot token.
- Files: `app/obs/redaction.py`, `tests/obs/test_redaction.py`
- Depends on: U-01
- Parallel: yes
- Guardrails: guardrail-python
- Criteria:
  1. Given a log record with a mail body, When emitted, Then the body is replaced (security; AC-14, AC-24).
  2. Given a URL `https://api.telegram.org/bot<token>/…`, When logged, Then the token part is masked (security; AC-24).
  3. Given an exception whose message contains the API key, When sent to Sentry, Then the key is scrubbed (security; AC-24).
  4. Given a Sentry event with local variables, When sent, Then variable values for secrets and bodies are removed (security).
  5. Given normal log lines, When emitted, Then ids and counts stay readable (edge).

### U-mail-triage-18: Container and deployment

- Layer: infra
- Contract: Dockerfile, compose service, Helm values and network policy for `mail-triage`; secrets from environment or Kubernetes secrets.
- Files: `agents/mail-triage/Dockerfile`, `compose.yaml`, `deploy/charts/component/values-mail-triage.yaml`, `tests/infra/*`
- Depends on: U-01
- Parallel: yes
- Guardrails: guardrail-docker, guardrail-compose, guardrail-kubernetes, guardrail-helm
- Criteria:
  1. Given the image, When started, Then the process is non-root with a read-only root filesystem and no extra capabilities (security; AC-30).
  2. Given the chart values, When rendered and linted, Then a network policy allows only Gmail, Anthropic, Telegram and PostgreSQL, and no ingress exists (security; AC-30).
  3. Given the deployment, When rendered, Then replicas is 1 with a strategy that never runs two copies at once (edge; design).
  4. Given the rendered manifests and image, When scanned, Then they contain no secret value (security).
  5. Given the compose profile `dev`, When started, Then the service starts with a Postgres container and fake secrets from `.env` (happy).

### U-mail-triage-19: End-to-end check (manual, with a test account)

- Layer: e2e
- Contract: a runbook and a script that run the whole flow against a Gmail test account and a test bot; no automated CI run with real accounts.
- Files: `docs/reviews/mail-triage-e2e.md`, `agents/mail-triage/scripts/e2e_seed.py`
- Depends on: U-10, U-13, U-14, U-15, U-16, U-17, U-18
- Parallel: no
- Guardrails: guardrail-pytest
- Criteria:
  1. Given a test mailbox, When a personal request, a newsletter and an automatic notice arrive, Then the first alerts Marco and the other two are only filed (happy; AC-3, AC-4).
  2. Given the alert, When "Reply" is used and confirmed, Then the mail arrives at the test sender and no reminder follows (happy; AC-7).
  3. Given "remind me later" with a short time, When it passes, Then one new alert arrives (happy; AC-9).
  4. Given an injected mail, When processed, Then nothing is sent or deleted (security; AC-19).
  5. Given the whole run, When finished, Then no mail was deleted and the logs contain no body or token (security; AC-2, AC-24).

## Coverage of spec criteria

| AC | Unit(s) |
|---|---|
| AC-1 | U-04, U-05, U-10, U-19 |
| AC-2 | U-05, U-10, U-19 |
| AC-3 | U-10, U-12, U-13, U-19 |
| AC-4 | U-10, U-19 |
| AC-5 | U-02, U-13 |
| AC-6, AC-7 | U-02, U-06, U-14, U-19 |
| AC-8 | U-02, U-14 |
| AC-9 | U-02, U-03, U-15, U-19 |
| AC-10 | U-02, U-15 |
| AC-11, AC-15 | U-11 |
| AC-12 | U-05, U-08, U-09, U-10, U-13 |
| AC-13 | U-04 |
| AC-14, AC-24 | U-01, U-07, U-08, U-11, U-17, U-19 |
| AC-16 | U-06, U-12 |
| AC-17 | U-14 |
| AC-18 | U-04, U-08 |
| AC-19 | U-08, U-19 |
| AC-20 | U-09, U-14 |
| AC-21 | U-04, U-12 |
| AC-22 | U-09, U-13, U-14 |
| AC-23 | U-05, U-08, U-12 |
| AC-25 | U-07 |
| AC-26 | U-08, U-10, U-13 |
| AC-27 | U-10 |
| AC-28 | U-05, U-06 |
| AC-29 | U-05, U-06, U-14 |
| AC-30 | U-18 |
| AC-31 | U-03, U-16 |
| AC-32 | U-03, U-10, U-13, U-15 |

Every AC in the spec appears at least once. Self-check against the "too big" signals: the largest unit (U-08) has 8 criteria and U-14 has 8, both within 3–10; no unit lists more than about 4 files.

## Notes and risks for the builders

- U-07 depends on the `oauth_token` table from U-09; build U-09 first or together.
- The Gmail and Telegram adapters are tested against fakes and recorded responses; real accounts are used only in U-19 and never in CI.
- Marco provides the Anthropic API key, the Telegram bot token and a Google OAuth client before U-19, not before.
- The threat model is delivered by tests (security criteria); `red-team` and `code-reviewer` check them in phase 6.
