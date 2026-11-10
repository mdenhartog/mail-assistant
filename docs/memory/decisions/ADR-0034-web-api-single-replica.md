---
id: ADR-0034
title: "The web api runs as one replica with in-process rate limits"
status: accepted
area: architecture
tags: [web, rate-limit, kubernetes, availability]
date: 2026-11-10
guardrails: [guardrail-fastapi, guardrail-kubernetes]
---

## Context

AC-16 asks for at most 30 requests a minute per client on sign-in and on the settings API, and a body limit of 8 KB. The first design kept the counters in a PostgreSQL table so the limit is exact across replicas. The round table found two problems: every unauthenticated request then writes to the database that the mail agent also uses, so a flood becomes database load, and a client address taken from `X-Forwarded-For` can be spoofed unless the proxy chain is pinned. The page has one user.

## Decision

The api runs as **one replica** (decision of Marco, 2026-11-10); the chart sets `replicas: 1` and a test renders it. Rate limits are in-process, in a fixed window per client and bucket (`signin`, `api`), configured by settings so tests can lower them.

- The client address is the address the last trusted proxy appended to `X-Forwarded-For`; trusted proxies are the ingress pod CIDR and a hop count, both configured. A request from any other peer is keyed by its own address.
- The limit is checked before any `login_flow` row is written, and the number of open `login_flow` rows has a cap above which sign-in answers 429.
- A refused request writes at most one security event per client and window.
- The ingress keeps a coarse limit and an 8 KB body cap as an outer line; the api enforces 8 KB itself.
- A rolling deploy briefly runs two pods; limits then restart per pod. This is accepted.

## Consequences

- No rate table, no per-request database round trip and no purge of rate rows.
- A second replica needs a new ADR that brings back a shared store.
- If the pod restarts, counters reset; acceptable for one owner.

## Alternatives

- Counters in PostgreSQL: exact across replicas, but ties request floods to the shared database; rejected.
- Limits only at the ingress: depends on the controller and cannot be tested in this repository; kept only as a backstop.
