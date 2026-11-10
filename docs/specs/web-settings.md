---
feature: web-settings
intent: INT-002
extends: adjustable-quiet-hours
status: approved
date: 2026-11-09
revised: 2026-11-10
approver: Marco
depends_on: adjustable-quiet-hours
---

# Web settings (login and settings page)

## Summary

The second feature of INT-002. It adds the first page of the web UI: a login page using a generic OIDC provider, and a settings page where Marco sees and changes the same four values as in Telegram (quiet hours, daily overview, remind-me-later default, time zone). It reuses the settings schema, the shared validation and the audit built in `adjustable-quiet-hours`, and it is the first internet-facing surface of the project. Marco wants more settings in the web UI later, so this page is the start of a settings area, not a one-off.

Why: Marco wants to manage settings in the web UI too, also when he travels (INT-002, S2).

This feature starts after `adjustable-quiet-hours` is built. The design questions (screens, style, clickable prototype under ADR-0009) are asked in phase 3 and are not decided here.

## Who it is for

Marco, the single owner, on phone, tablet and desktop. Mostly at a desk, sometimes on a phone abroad.

## Goals

1. Marco signs in on a login page through a configured OIDC provider (Google first) and nobody else can.
2. Marco sees and changes the four values on a settings page, with the same rules as Telegram.
3. Every change made on the web is announced in Telegram with old and new values and an Undo button.
4. A stale page cannot overwrite a change made elsewhere.

## Non-goals

- Passwords or accounts of our own, more than one user, roles.
- Other settings, an alert overview or any other page.
- Mail access: web sign-in asks only for identity scopes (`openid email profile`), never for Gmail or Calendar (ADR-0024).
- Automatic time-zone detection.

## Anti-goals (a failure even if it technically works)

- Someone else gets into the page or changes a value, also through a stolen session.
- A web change silences urgent alerts and Marco does not hear of it.
- The backend can read mail, alert content or tokens.
- The page works only on desktop or only with a mouse.

## Decisions made by Marco

| # | Decision | Source |
| --- | --- | --- |
| W1 | The web login is a login page with a generic OIDC provider chosen by configuration, not tied to Google. | brainstorm (ADR-0024) |
| W2 | The web UI shows and changes the same four values as Telegram. | INT-002 |
| W3 | Values are validated with the same rules as Telegram; a change applies to new alerts only. | INT-002, S7 of `adjustable-quiet-hours` |
| W4 | The page must be reachable from the internet (Marco travels). Confirmed 2026-11-10 (ADR-0032). | threat model question 1 |
| W5 | The feature is built in two releases: R1 first, R2 later (see Releases). | design round table, 2026-11-10 |
| W6 | A web change is announced with its own Undo token; Undo goes back to before the burst, and a lock button blocks web sign-in until Marco lifts it in Telegram (ADR-0033). | design round table, 2026-11-10 |
| W7 | The web api runs as one replica with in-process rate limits (ADR-0034). | design round table, 2026-11-10 |
| W8 | Visual direction: Pebble (ADR-0035). Clickable prototype first (ADR-0009), limited to the settings form and the conflict banner. | 2026-11-10 |

## My calls (Marco may change these)

- C-1: Only one account, identified by the exact pair (issuer, `sub`), may sign in. E-mail is shown, never used to decide access. The configuration (HTTPS issuer, non-empty `sub`) is checked at start; the backend refuses to start if it is wrong.
- C-2: Session: opaque id in a `__Host-session` cookie (`HttpOnly`, `Secure`, `SameSite=Lax`), stored in a backend-owned table; idle limit 30 minutes, absolute limit 12 hours; logout is a POST and ends the session on the server. Values used during sign-in (`state`, nonce, PKCE verifier) live in a short-lived single-use `__Host-` cookie.
- C-3: State changes need a CSRF token and a strict `Origin` check; no CORS. After sign-in only relative return paths from an allow-list are followed.
- C-4: Limits (set by configuration so tests can lower them): 30 requests a minute per client on sign-in and on the settings API, request body 8 KB.
- C-5: The page sends the row version it loaded; a save with an old version gets 409 and the page shows the new values. Typed values and the page survive an expired session: after signing in again Marco returns to the same page.
- C-6: The page shows who changed what last, for example "Last changed from Telegram at 14:02", and has a "Reset to defaults" button with confirmation.
- C-7: Time zone entry uses an autocomplete (combobox) with the same lookup and aliases as Telegram; the live local time in the chosen zone is shown while typing. Times use `type="time"` or a stepped select.
- C-8: The agent, at each run, looks at audit records written through the web since the last one it saw and sends one Telegram notice per change with old and new values, the channel and two buttons: Undo, which restores the values from before the first change Marco had not yet been told about, and "Undo and lock web sign-in" (ADR-0033). The notice has its own token record and never replaces a Telegram dialogue; quiet hours never hold it.
- C-9: Security events (refused sign-ins, session start and end, CSRF refusals, 429s) are logged with a hashed unknown `sub`, the issuer, the result and a request id, never tokens or codes. In R2, after 5 refused sign-ins (a valid token for the wrong account) within 10 minutes Marco gets a Telegram notice; protocol failures are logged and counted separately and never alert. Audit records are kept for 1 year (R2); the cleanup runs under the owner role as a step of the migrate job, not as a runtime role and not as a standing job with owner credentials.
- C-10: Production exposes only the web assets, `/api/settings` and `/auth/*`. `/docs`, `/redoc`, `/openapi.json`, health and metrics answer 404 from outside.
- C-11: Words match Telegram: "Quiet hours", "Daily overview", "Remind-me-later default", "Time zone", each with a one-line explanation. Refusals are human ("This account is not allowed for this app"), never a bare status code. The login page names the account to use and says that no mail access is requested.

## Behaviour

1. Marco opens the site, is sent to the login page, signs in at the provider, and lands on the settings page. Anyone else is refused.
2. The page shows the four values and the last-change line. Marco edits and saves; the page validates as Telegram does, and shows the reason next to the field.
3. A save stores the whole row with the version, writes the audit record, and shows the new values.
4. If the row changed since the page loaded, the page tells Marco and reloads the values.
5. The agent notices the web change at its next run and notifies Marco in Telegram.

## Acceptance criteria

| # | Criterion |
| --- | --- |
| AC-1 | **Given** a signed-in Marco, **when** he opens the settings page, **then** the four values and the last-change line are shown. |
| AC-2 | **Given** a visitor who is not signed in, **when** they open the page or call `/api/settings`, **then** they get the login page or 401 and nothing is shown. |
| AC-3 | **Given** an ID token with the right `sub` from another issuer, the right e-mail with another `sub`, or an unverified e-mail claim only, **when** the callback is processed, **then** it is refused (403) and no session is created. |
| AC-4 | **Given** an empty `sub`, an `http` issuer or a missing client secret in the configuration, **when** the backend starts, **then** it refuses to start. |
| AC-5 | **Given** a sign-in callback with a wrong `state`, a wrong nonce, a bad signature, an expired token, a wrong issuer, a wrong audience (or `azp`), or a `state` cookie of another browser, **when** it is processed, **then** each case is refused, one test each, and no session is created. |
| AC-6 | **Given** the token request, **then** the redirect URI is the exact registered one, and a `return_to` of `https://evil.example` ends at `/settings`. |
| AC-7 | **Given** a session, **then** its cookie is `__Host-session`, `HttpOnly`, `Secure`, `SameSite` Lax; it expires after 30 minutes idle and 12 hours absolute; it is invalid after logout; the session id changes at sign-in. |
| AC-8 | **Given** a settings change or logout without the CSRF token, with a wrong token, or with a wrong `Origin`, or sent as a GET, **then** it is refused and nothing changes. |
| AC-9 | **Given** a valid change, **when** Marco saves, **then** it is stored with the audit record, and the agent uses it at its next run. |
| AC-10 | **Given** an invalid value, **when** Marco saves, **then** the field shows the reason (same rules as Telegram, same shared validation) and nothing is stored. |
| AC-11 | **Given** the page loaded at version 1 and Telegram changed the row to version 2, **when** Marco saves, **then** the save is refused with 409, the page shows the new values and says so. |
| AC-12 | **Given** a session that expires while the form is open, **when** Marco saves, **then** nothing is stored and he is sent to sign in, and afterwards returns to `/settings` with the stored values (R1); his typed values are kept and restored, never saved automatically (R2). |
| AC-13 | **Given** a change made on the web, **when** the agent next runs (within one run interval, which the page states), **then** Marco gets one Telegram notice with old value, new value, channel, change number, Undo and "Undo and lock web sign-in"; after several web changes before the agent runs, Undo on any notice restores the values from before the first of them and writes one audit record; a pending Telegram dialogue is not replaced; quiet hours do not hold the notice. |
| AC-14 | **Given** a value containing markup or script, **when** it is shown or refused, **then** it is rendered as text, and the page sends a Content-Security-Policy that blocks inline scripts (checked by header and in a browser). |
| AC-15 | **Given** any API error, **then** the body is generic; the API returns only the four values, the version and the update info; the generated OpenAPI paths equal an allow-list and every state-changing operation needs a session and the CSRF check. |
| AC-16 | **Given** more than 30 requests in a minute from one client on sign-in or the settings API (one api replica, in-process limits; the client address is the one the last trusted proxy appended), **then** further requests get 429 before any sign-in row is written; a body over 8 KB is refused; the number of open sign-in flows is capped. |
| AC-17 | **Given** the backend's database role, **when** it reads mail items, alert content or the token store, or has any privilege on the audit table, or sets `version`, `updated_via` or `updated_by` to a value the guard does not allow, or runs DDL, **then** PostgreSQL refuses (SQLSTATE 42501); and a settings write whose audit insert fails is rolled back. |
| AC-18 | **Given** a plain HTTP request, **then** it is redirected to HTTPS and responses carry HSTS. |
| AC-19 | **Given** `/docs`, `/redoc`, `/openapi.json`, health or metrics requested from outside, **then** the answer is 404. |
| AC-20 | **Given** a refused sign-in, a CSRF refusal or a 429, **then** one security log entry per client and window exists (result, issuer, hashed `sub`, request id) without token or code, and no query string appears in any log (R1); after 5 refused sign-ins in 10 minutes Marco gets one Telegram notice, protocol failures never alert (R2). |
| AC-21 (R2) | **Given** audit records older than 1 year, **when** the cleanup runs under the owner role as a step of the migrate job, **then** they are removed. |
| AC-22 | **Given** the login page, the settings page and the error states (loading, saving, save failed, validation error, 403, session expired) at 320, 375, 768 and 1280 px and at 200 % text size, **then** there is no horizontal scroll and axe finds no violation. |
| AC-23 | **Given** keyboard-only use, **then** the whole flow can be done, focus is visible, focus moves to the first invalid field on submit, errors are announced (`aria-live`/`role=alert`, linked with `aria-describedby`), targets are at least 24 px (44 px on touch), and the Save button is disabled while saving. |
| AC-24 | **Given** the login page, **then** it names the account to use and says that no mail access is requested; a refused account sees "This account is not allowed for this app". |
| AC-25 (R2) | **Given** Reset to defaults and its confirmation, which names the values including the time zone, **then** the defaults are stored through the same validated write and audited. |
| AC-26 | **Given** the agent and the backend, **then** both agree on the settings schema through the shared contract test fixture of `adjustable-quiet-hours`. |
| AC-27 | **Given** an active web session, **when** Marco taps "Undo and lock web sign-in", **then** the next call with that session gets 401, a callback for the allowed account gets 403, and the lock is lifted only by a Telegram command. |
| AC-28 | **Given** a zone change on the page, **then** the zone is the first field, a preview shows what the quiet hours mean in the new zone, and the saved banner states the time and the notice interval; **given** a conflict, **then** the page keeps Marco's own values next to the new ones ("Use mine" and "Keep Telegram's"). |

## Test infrastructure (from the round table)

A local fake OIDC provider (configurable signing key and claims, no real Google), a fixed seed for the settings table, Playwright against the prod-like compose profile at 375/768/1280 with axe, a database test that connects as the backend role, and a prod-like check for the HTTPS redirect and HSTS.

## Releases

- **R1:** AC-1 to AC-11, the first half of AC-12, AC-13 to AC-19, the first half of AC-20, AC-22 to AC-24, AC-26 to AC-28.
- **R2:** the second half of AC-12, the second half of AC-20, AC-21 and AC-25.

## Open points before staging

- Domain, certificate issuer, cluster and ingress controller (ADR-0012, ADR-0032).
- The agent's run interval that the page text quotes.
- The ADR-0024 corrections are made together with this spec's approval.
