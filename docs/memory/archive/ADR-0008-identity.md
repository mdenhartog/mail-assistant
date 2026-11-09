---
id: ADR-0008
title: "Identity: Google OAuth2"
status: superseded
area: identity
tags: [oauth2, google, authentication]
date: 2026-11-08
guardrails: [guardrail-oauth2-oidc]
---
## Context

The mail assistant integrates with Gmail and Google Calendar. Users need to log in and grant the app access to their Google account.

## Decision

Authentication uses **Google OAuth2** (OIDC profile):

- The Gmail and Google Calendar OAuth2 flow is reused for identity — no separate IdP.
- Scopes requested at login: `openid email profile` + Gmail + Calendar scopes.
- Sessions are managed server-side (backend issues JWT access tokens; refresh tokens stored encrypted in the database).
- PKCE is mandatory for the web flow.

## Consequences

- Single OAuth2 consent covers identity and API access — reduces friction for users.
- If Microsoft 365 support is added, a second IdP (Entra ID) must be added (new ADR).
- The guardrail `guardrail-oauth2-oidc` applies to all auth code.

## Alternatives

- Microsoft Entra ID — deferred: no Outlook integration in scope yet.
- Auth0 / Supabase Auth — rejected: adds an external dependency; Google OAuth2 is sufficient and directly integrated.
