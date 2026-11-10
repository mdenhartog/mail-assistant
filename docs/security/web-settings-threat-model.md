---
feature: web-settings
intent: INT-002
spec: docs/specs/web-settings.md
extends: adjustable-quiet-hours-threat-model
status: approved
date: 2026-11-09
revised: 2026-11-10
approver: Marco
asvs: "5.0"
---

# Threat model: web settings

The Telegram part is in `adjustable-quiet-hours-threat-model.md`.

## Scope

A login page where Marco gives a username and a one-time code sent by e-mail (ADR-0036), the settings page in `apps/web`, the settings API in `backend`, the backend's session and login-request tables, the backend's send-only SMTP credential, and the backend's access to the `settings` schema (ADR-0025). The page is reachable only from the local network (ADR-0037); there is no public ingress and no public DNS name.

## Data classification

| Data | Class | Note |
| --- | --- | --- |
| Session cookie, login cookie, one-time code | secret | The code is short-lived (10 minutes, single use) and stored only as an HMAC-SHA-256 hash. Never in a URL, a log, an error or a subject line. |
| SMTP credential (send-only account) | secret | SealedSecret (ADR-0029), never in code. |
| Code-hash key, CSRF key | secret | At least 32 random bytes, SealedSecret. |
| E-mail address of Marco | personal data | Configured on the server, shown masked, never taken from the request, never logged in full. |
| Allowed username | internal | Configuration. An unknown username is never logged in clear. |
| Quiet hours, overview time, reminder default | internal | See the Telegram model. |
| Time zone | personal data (low) | Reveals travel location. |
| Security event log | internal | Result, hashed username when unknown, request id. |

## Diagram

```text
Browser ──[B1: local network, TLS from a private CA]──► ingress (private address) ──► web app ──► backend API ──[B2: backend DB role, schema settings + own web_auth tables]──► PostgreSQL
backend API ──[B3: SMTP, STARTTLS, verified certificate, send-only account]──► SMTP relay ──► Marco's mailbox ──(code read by Marco, typed into the page)──► Browser
(test and dev only) backend API ──► local mail catcher, port 8025 ──► tests read the code
agent ──(reads audit records written via web; notifies Marco)──► Telegram
```

The trust boundary B1 is the local network: anything on it can reach the login page. There is no identity provider and no outbound call to one. An archify data-flow diagram is added with the design in phase 3.

## What the local-only decision removes and what remains

Removed (ADR-0037): scanning and probing from the internet, a public certificate and public DNS, a public load balancer. Remains: any device or person on the local network, a mistake in the network setup (for example a port forward or a bridged guest network), a misrouted exposure of the ingress, and Marco's mailbox, which is outside the network. The limits, the attempt counters, the session rules, the lock and the audit stay as designed.

## Threats

| id | element | STRIDE | threat | L | I | mitigation | criterion | ASVS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| W-1 | B1 page and API, code check | S | A visitor on the local network or someone who knows the username guesses the code, replays a used or expired code, uses a code in another browser, or opens the API without a session; an empty or wrong configuration lets anyone in. | M | H | Six-digit code from a secure generator, valid 10 minutes, single use, 5 wrong attempts kill it, a new code replaces the old one, hash compared in constant time, bound to the browser by the `__Host-login` cookie holding the login request id; the configuration (username, address, SMTP settings, code-hash key of at least 32 bytes) is checked at start and the backend refuses to start otherwise; the API checks the session on the server. | AC-2, AC-3, AC-4, AC-5, AC-31 | V6, V8, V10 |
| W-2 | B1 request-code and verify-code | I, S | Username enumeration through response differences, timing or status; a code taken from the request or the address chosen by the caller. | M | M | The answer, status, cookies and timing class are the same for a known and an unknown username ("If this username is known, a code has been sent"); the e-mail address comes only from server configuration and is shown masked; `return_to` limited to an allow-list of relative paths; generic 400 for any code failure. | AC-6, AC-30 | V6, V16 |
| W-3 | B1 session | S, E | Session theft or reuse; cookie tossing by a sibling subdomain; a stateless token that cannot be revoked. | M | H | Opaque server-side session in a `__Host-session` cookie (`HttpOnly`, `Secure`, `SameSite=Lax`); idle 30 min, absolute 12 h; logout is a POST and ends the session on the server; the id changes at sign-in. | AC-7 | V7, V3 |
| W-4 | B1 change endpoints | T | A cross-site request forges a change or a logout. | M | H | CSRF token and strict `Origin` check on every state-changing call; state changes only by POST or PUT; no CORS. | AC-8 | V3 |
| W-5 | settings page | T, I | Script injection into the page. | L | H | React escaping, no raw HTML, a strict Content-Security-Policy without inline scripts, `X-Content-Type-Options`, `frame-ancestors`. | AC-14 | V3, V1 |
| W-6 | B1 API | I | The API or errors reveal more than needed; FastAPI docs and OpenAPI are reachable; health and metrics are reachable. | M | M | Generic error bodies; the API returns only the four values, the version and update info; the ingress exposes only the web assets, `/api/*` and `/auth/*`; docs, OpenAPI, health and metrics return 404; the route allow-list is tested. | AC-15, AC-19 | V13, V16 |
| W-7 | B1 sign-in and API | D | A flood of requests or oversized bodies; code-request abuse that floods Marco's mailbox with codes or locks him out by using up the hourly cap. | M | M | 30 requests a minute per client; body limit 8 KB; timeouts; a new code only after 60 seconds and at most 5 codes an hour per username; in-process limits with one api replica (ADR-0034); limits checked before any login request row is written; open login requests capped. | AC-16, AC-31 | V2 |
| W-8 | B2 database role | E | The backend's role can read mail, alert content or tokens, change audit rows, or alter the schema. | M | H | A separate owner role runs migrations; the backend role gets only what it needs on `settings` plus its own session and login-request tables, and can only insert into the audit table; neither runtime role owns anything; a settings write and its audit insert are one transaction. | AC-17 | V8, V13 |
| W-9 | B1 transport | I | Settings, session and code travel in clear text on the local network; the certificate of the private CA expires unnoticed. | L | H | TLS at the ingress with a certificate from a private CA that Marco's devices trust (guardrail-tls-certificates), HSTS without `includeSubDomains` and no preload, HTTP redirect, expiry monitoring at least 14 days ahead. | AC-18 | V12 |
| W-10 | web changes | R | A web change is not attributable. | M | M | The same append-only audit record as in the Telegram model, with the configured username as actor (hashed in `updated_by`). | AC-9 | V16 |
| W-11 | stolen session or mailbox | T, S | Someone who reads Marco's mailbox, or holds his session, signs in and shifts the zone or hours so that urgent alerts are held, and the confirmation is shown only on the page the attacker uses. | M | H | Every web change is announced out of band: at the next run the agent sends Marco a Telegram notice with old and new values, the channel and Undo and "Undo and lock web sign-in" buttons. Optional later: re-authentication for writes. See accepted risk R-1. | AC-13, AC-27 | V6, V16 |
| W-12 | stale form | T | A saved page overwrites a change made in Telegram, or a double submit writes twice. | M | M | The page sends the row version; an old version gets 409 and the page reloads the values; the Save button is disabled while saving. | AC-11, AC-23 | V2 |
| W-13 | security events | R | A slow guessing or takeover attempt is invisible; audit rows grow without limit. | M | M | Security events are logged (wrong, expired and reused codes, refused code requests, session start and end, CSRF refusals, 429s) with result and request id; 5 wrong or expired codes in 10 minutes alert Marco in Telegram (R2); audit retention is 1 year with a cleanup under the owner role. | AC-20, AC-21, AC-31 | V16 |
| W-14 | B3 e-mail in transit and in the mailbox | I | The e-mail with the code is read in transit between the backend and the relay, or by a mail scanner or preview; a link in the mail is fetched before Marco uses it. | L | H | SMTP with STARTTLS and a verified certificate (start-up refuses a non-STARTTLS setting); no link in the mail, so nothing to prefetch; the code is not in the subject; the mail carries no request details; the code is short-lived and single use. Mailbox compromise is accepted risk R-1. | AC-4, AC-29 | V12, V6 |
| W-15 | logs, errors and responses | I | The code, the full username or the e-mail address appears in a log, an error, a URL or a response. | M | H | Only the HMAC-SHA-256 hash of the code is stored; the code is never in a URL (it is posted in a body), a log or an error; security events carry no code and no full unknown username; responses show only the masked address; no query string appears in any log (grep test in the prod-like job). | AC-20, AC-29, AC-30 | V16, V14 |
| W-16 | B3 SMTP credential | I, E | The send-only SMTP credential leaks or is used to send other mail. | L | M | The account is send-only and has no mailbox access; the credential is a SealedSecret (ADR-0029), never in code, values or logs; egress from the api to SMTP is limited to the configured host and port; sending failures answer with a generic message and never show the cause. | AC-4, AC-29 | V13, V12 |
| W-17 | B1 other devices on the local network, misrouted exposure | S, D | A device on the local network, a guest on a bridged network or a wrongly forwarded port reaches the login page and tries codes or floods requests. | M | M | The code, attempt, cooldown and hourly limits and the in-process request limits apply to every client; the ingress admits only the web assets, `/api/*` and `/auth/*`; no public ingress or DNS exists; exposing the page to the internet needs a new decision and a new threat model review (ADR-0037). | AC-16, AC-19, AC-31 | V2, V13 |

All six STRIDE types are covered: S (W-1 to W-3, W-11, W-17), T (W-4, W-5, W-11, W-12), R (W-10, W-13), I (W-2, W-5, W-6, W-9, W-14 to W-16), D (W-7, W-17), E (W-3, W-8, W-16).

## Accepted risks

| # | Risk | Reason |
| --- | --- | --- |
| R-1 | Whoever reads Marco's mailbox can sign in. | Marco chose an e-mailed one-time code (ADR-0036). Two-step verification on the mailbox is a condition for production. The out-of-band Telegram notice (W-11) limits the damage, Undo reverses it back to before the burst and the lock stops further web sign-in (ADR-0033). Reviewed on 2027-05-10. |
| R-2 | Anything on the local network can reach the login page. | Marco chose local-only access (ADR-0037). The code limits and the request limits bound guessing and flooding; a mistake in the network setup is a residual risk. |

## Open questions

1. W4 is decided: the page is reachable only locally (ADR-0037); the sign-in is an e-mailed code (ADR-0036).
2. Phase 3 decided: CSRF and limits live in the backend, with one api replica (ADR-0034); the session design is in `docs/design/web-settings-design.md`.
3. ASVS references are to chapters of ASVS 5.0; exact requirement ids are added when the plan is made.
4. The local host name, the private certificate authority and the SMTP account are decided before staging.

## Delta 2026-11-10 (phase 3 round table)

| id | change |
| --- | --- |
| W-4 | The CSRF token is derived (`HMAC(csrf_key, session_id)`) and served only to a same-origin `GET /api/session`; two tabs on one session both work. |
| W-7 | One api replica with in-process limits (ADR-0034). The client address is the one the last trusted proxy appended, so a spoofed leftmost `X-Forwarded-For` does not give a fresh bucket; the limit is checked before any login request row is written; open login requests are capped; one security event per client and window. |
| W-8 | The web role's column grant includes `version`, `updated_via` and `updated_by` (without them every save fails); the guard checks that `updated_by` matches `web:` and 32 hex characters; every new function is revoked from `PUBLIC`; the database URL uses `sslmode=verify-full`. |
| W-9 | TLS 1.2 minimum at the ingress, a certificate expiry alert at least 14 days ahead, and a single peer (namespace and pod selector) in the ingress NetworkPolicy. |
| W-11 | Own token record for web notices, Undo back to before the burst, "Undo and lock web sign-in" with `web_auth.web_lock`, and quiet hours never hold the notice (ADR-0033). The notice is selected by `db_role` and ordered by the version as an integer. |
| W-13 | Logs never contain the query string: api access log off, request logging without queries, ingress and edge formats without them, `httpx` and `httpcore` loggers at WARNING; a grep test in the prod-like job. The alert counts wrong and expired codes only (R2). Retention (R2) runs under the owner role as a migrate job step; no standing job holds owner credentials. |

## Delta 2026-11-10 (sign-in by e-mailed code and local-only access)

Caused by ADR-0036 (replaces ADR-0024) and ADR-0037 (replaces ADR-0032).

| id | change |
| --- | --- |
| W-1 | Rewritten: guessing and replaying codes, a code used in another browser, and configuration errors replace the identity-provider checks. Criteria AC-3 to AC-5 and AC-31. |
| W-2 | Rewritten: username enumeration and response or timing differences replace the OIDC flow threats. The mix-up, discovery, JWKS, SSRF and redirect-URI rows are removed because there is no identity provider and no outbound identity call. Criteria AC-6 and AC-30. |
| W-7 | Extended with code-request abuse and mail flooding, bounded by the 60 second cooldown, 5 codes an hour and the in-process limits. |
| W-9 | The certificate comes from a private certificate authority; HSTS has no `includeSubDomains` and no preload (ADR-0037). |
| W-10 | The actor is the configured username (hashed), not an issuer and `sub`. |
| W-11 | The stolen-account case becomes mailbox compromise (R-1, restated). |
| W-13 | The alert counts wrong and expired codes; refused code requests are events too. |
| W-14 to W-17 | New: e-mail interception (I), codes, username and address in logs and responses (I), the SMTP credential (I, E), other devices on the local network and a misrouted exposure (S, D). |
| R-1 | Restated: whoever reads Marco's mailbox can sign in; two-step verification on the mailbox is a condition for production; R-2 added for the local network. |
| Data | Added: one-time code, SMTP credential, code-hash key, e-mail address. |
