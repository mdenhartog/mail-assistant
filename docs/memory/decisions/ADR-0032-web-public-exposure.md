---
id: ADR-0032
title: "The web settings page is reachable from the internet"
status: accepted
area: hosting
tags: [web, ingress, tls, exposure, mail-triage]
date: 2026-11-10
guardrails: [guardrail-kubernetes, guardrail-tls-certificates, guardrail-oauth2-oidc]
---

## Context

The spec assumed the settings page must be reachable from the internet because Marco travels (W4), and the threat model left that as an open question. Alternatives were a VPN or private network only.

## Decision

The page is public on the internet over HTTPS (decision of Marco, 2026-11-10). Protection rests on the controls of the threat model: OIDC sign-in for exactly one (issuer, `sub`), server-side sessions, CSRF with an `Origin` check, rate limits, a strict CSP, HSTS, a narrow database role, and a Telegram notice with Undo for every change made on the web (W-11).

- The ingress exposes only the web assets, `/api/*` and `/auth/*`; docs, OpenAPI, health and metrics answer 404 from outside (AC-19).
- Plain HTTP redirects to HTTPS and responses carry HSTS (AC-18).
- Domain, certificate issuer and the cluster with its ingress controller are not chosen yet. They are needed before production (ADR-0012 left them open) and are decided with the release plan; they block the production values, not the build.

## Consequences

- The first internet-facing surface of the project: security criteria AC-2 to AC-8 and AC-14 to AC-20 are release gates, and a black-box penetration test on staging is part of the release (phase 9).
- Let's Encrypt with HTTP-01 is possible (public reachability).
- A stolen provider account can sign in; the out-of-band Telegram notice limits and reverses the damage (accepted risk R-1).

## Alternatives

- VPN or private network only: much smaller attack surface, but a connection is needed first, also abroad, and the certificate needs DNS validation or a private CA. Not chosen by Marco.
