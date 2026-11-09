---
id: ADR-0024
title: "Web sign-in: generic OIDC provider, identity scopes only"
status: accepted
area: identity
tags: [oidc, oauth2, authentication, web]
date: 2026-11-09
supersedes: ADR-0008
guardrails: [guardrail-oauth2-oidc]
---

## Context

ADR-0008 fixed Google OAuth2 as the identity and reused the Gmail/Calendar consent for login. INT-002 adds the first web page, which only changes settings. Marco wants to reach it with his own account through a standard login page, without the page being tied to Google.

## Decision

The web UI has a login page that signs in through a **generic OIDC provider**, configured by deployment settings (issuer URL, client id, client secret), not by user input. Google is the first configured provider, and it can be replaced by any OIDC provider without code change. The scopes requested at web sign-in are identity only: `openid email profile`. Access to Gmail (and later Calendar) stays a separate consent given to the agent and is never part of web sign-in. The allowed account is one configured pair (issuer, `sub`). Authorization code flow with PKCE, `state` and `nonce`, exact redirect URI. Access is decided only by the exact pair (issuer, `sub`); the e-mail is never used for it. The backend keeps an opaque server-side session (an id in a `__Host-` cookie, stored in a backend-owned table with idle and absolute expiry); it holds no provider tokens beyond sign-in and issues no JWT.

## Consequences

- The web UI can switch identity provider by configuration; replacing it needs no code change.
- Web sign-in no longer grants mail access, which narrows what a stolen web session can do.
- The Gmail consent of the agent (ADR-0011) is not changed.
- Provider discovery runs only against the configured issuer over TLS (no user-supplied URL, so no SSRF).
- ADR-0008 is superseded and archived. PKCE stays mandatory; its JWT access tokens and stored refresh tokens are dropped, as is the statement that Gmail scopes are requested at login.
- A second issuer needs a new ADR (mix-up defence: RFC 9207 `iss` in the response or a redirect URI per issuer).

## Alternatives

- Own accounts with passwords: more attack surface (storage, reset, brute force) for one user; rejected by Marco in favour of OIDC.
- Both password login and OIDC: most work and surface; rejected.
- Keep ADR-0008 unchanged: ties the page to Google and bundles mail scopes into login; rejected.
