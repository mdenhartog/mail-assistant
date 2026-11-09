---
feature: web-settings
intent: INT-002
spec: docs/specs/web-settings.md
extends: adjustable-quiet-hours-threat-model
status: approved
date: 2026-11-09
approver: Marco
asvs: "5.0"
---

# Threat model: web settings

The Telegram part is in `adjustable-quiet-hours-threat-model.md`.

## Scope

The first internet-facing page of the project: a login page with a generic OIDC provider (ADR-0024), the settings page in `apps/web`, the settings API in `backend`, the backend's session table, and the backend's access to the `settings` schema (ADR-0025).

## Data classification

| Data | Class | Note |
| --- | --- | --- |
| Session cookie, ID token, authorization code | secret | Never in a URL, a log or an error. |
| OIDC client secret | secret | Kubernetes secret, never in code. |
| Allowed account (issuer and `sub`) | internal | Configuration. |
| Quiet hours, overview time, reminder default | internal | See the Telegram model. |
| Time zone | personal data (low) | Reveals travel location. |
| Security event log | internal | Hashed unknown `sub`, issuer, result, request id. |

## Diagram

```text
Browser ──[B1: internet, TLS]──► ingress ──► web app ──► backend API ──[B2: backend DB role, schema settings + own session table]──► PostgreSQL
Browser ◄──[B3: OIDC redirect]──► OIDC provider (Google first)
agent ──(reads audit records written via web; notifies Marco)──► Telegram
```

An archify data-flow diagram is added with the design in phase 3.

## Threats

| id | element | STRIDE | threat | L | I | mitigation | criterion | ASVS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| W-1 | B1 page and API | S | A visitor or another account at the provider opens the settings or calls the API; the identity check weakens by using the e-mail; an empty or wrong configuration lets anyone in. | H | H | Only the exact pair (issuer, `sub`) may continue; e-mail is display only; configuration is checked at start (HTTPS issuer, non-empty `sub`, client secret) and the backend refuses to start otherwise; the API checks on the server. | AC-2, AC-3, AC-4 | V8, V10 |
| W-2 | B3 OIDC flow | S | Login CSRF, code interception, redirect abuse, mix-up with another issuer, an open redirect after sign-in, pre-login values not bound to the browser. | M | H | Authorization code flow with PKCE, `state` and nonce in a single-use `__Host-` cookie, exact redirect URI, ID token signature, issuer, audience (and `azp`) and expiry checked, discovery only against the configured issuer over TLS, identity scopes only, `return_to` limited to an allow-list of relative paths. A second issuer needs a new ADR. | AC-5, AC-6 | V10 |
| W-3 | B1 session | S, E | Session theft or reuse; cookie tossing by a sibling subdomain; a stateless token that cannot be revoked. | M | H | Opaque server-side session in a `__Host-session` cookie (`HttpOnly`, `Secure`, `SameSite=Lax`); idle 30 min, absolute 12 h; logout is a POST and ends the session on the server; the id changes at sign-in. | AC-7 | V7, V3 |
| W-4 | B1 change endpoints | T | A cross-site request forges a change or a logout. | M | H | CSRF token and strict `Origin` check on every state-changing call; state changes only by POST or PUT; no CORS. | AC-8 | V3 |
| W-5 | settings page | T, I | Script injection into the page. | L | H | React escaping, no raw HTML, a strict Content-Security-Policy without inline scripts, `X-Content-Type-Options`, `frame-ancestors`. | AC-14 | V3, V1 |
| W-6 | B1 API | I | The API or errors reveal more than needed; FastAPI docs and OpenAPI are public; health and metrics are public. | M | M | Generic error bodies; the API returns only the four values, the version and update info; the ingress exposes only the web assets, `/api/settings` and `/auth/*`; docs, OpenAPI, health and metrics return 404 from outside; the route allow-list is tested. | AC-15, AC-19 | V13, V16 |
| W-7 | B1 sign-in and API | D | A flood of sign-ins or requests, or oversized bodies. | M | L | 30 requests a minute per client; body limit 8 KB; timeouts. | AC-16 | V2 |
| W-8 | B2 database role | E | The backend's role can read mail, alert content or tokens, change audit rows, or alter the schema. | M | H | A separate owner role runs migrations; the backend role gets only what it needs on `settings` plus its own session table, and can only insert into the audit table; neither runtime role owns anything; a settings write and its audit insert are one transaction. | AC-17 | V8, V13 |
| W-9 | B1 transport | I | Settings and session travel in clear text; certificate expiry goes unnoticed. | L | H | TLS at the ingress (guardrail-tls-certificates), HSTS, HTTP redirect, expiry monitoring. | AC-18 | V12 |
| W-10 | web changes | R | A web change is not attributable. | M | M | The same append-only audit record as in the Telegram model, with the account (issuer and `sub`) as actor. | AC-9 | V16 |
| W-11 | stolen session or provider account | T, S | An attacker with Marco's session at the provider signs in and shifts the zone or hours so that urgent alerts are held, and the confirmation is shown only on the page the attacker uses. | M | H | Every web change is announced out of band: at the next run the agent sends Marco a Telegram notice with old and new values, the channel and an Undo button. Optional later: re-authentication for writes. | AC-13 | V6, V16 |
| W-12 | stale form | T | A saved page overwrites a change made in Telegram, or a double submit writes twice. | M | M | The page sends the row version; an old version gets 409 and the page reloads the values; the Save button is disabled while saving. | AC-11, AC-23 | V2 |
| W-13 | security events | R | A slow takeover attempt is invisible; audit rows grow without limit. | M | M | Security events are logged (refused sign-ins, session start and end, CSRF refusals, 429s) with hashed unknown `sub`, issuer, result and request id; 5 refusals in 10 minutes alert Marco in Telegram; audit retention is 1 year with a cleanup under the owner role. | AC-20, AC-21 | V16 |

All six STRIDE types are covered: S (W-1 to W-3, W-11), T (W-4, W-5, W-11, W-12), R (W-10, W-13), I (W-5, W-6, W-9), D (W-7), E (W-3, W-8).

## Accepted risks

| # | Risk | Reason |
| --- | --- | --- |
| R-1 | Anyone who controls Marco's account at the provider can sign in. | Marco chose a generic OIDC login without a second factor of our own; the provider's own protection applies. The out-of-band Telegram notice (W-11) limits the damage and Undo reverses it. |

## Open questions

1. Is the page reachable from the internet (W4 in the spec)? Marco travels, so this is assumed.
2. Where CSRF and rate limits live (middleware or ingress), the session table design and the public ingress: phase 3.
3. ASVS references are to chapters of ASVS 5.0; exact requirement ids are added when the plan is made.
