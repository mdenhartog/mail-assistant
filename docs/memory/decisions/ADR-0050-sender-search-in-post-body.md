---
id: ADR-0050
title: "The sender search of the review items is a POST with the text in the body, never a GET with a query parameter"
status: accepted
area: security
tags: [mail-categories, privacy, api, web]
date: 2026-11-17
guardrails: [guardrail-fastapi, guardrail-pydantic, guardrail-tanstack-query]
---

## Context

The user asked to filter and sort the mails of a review by sender (AC-58, AC-59). A sender name or address is personal data (ADR-0044, AC-30). A GET query parameter ends up in access logs, proxy logs, browser history and the Referer header; the project rule is that no secret or personal data is in a URL.

## Decision

The search is `POST /api/plan/items/search` with a strict JSON body (sender text up to 100 characters, a closed sort set, order, page, category ids). The existing GET route keeps its contract and has no sender parameter. The sender text is matched case-insensitively against name or address with `ILIKE` and escaped wildcards; the ORDER BY is one literal statement with bound parameters. Error answers never echo the text.

## Consequences

- No sender text in a URL, access log or browser storage; the TanStack Query key holds it in memory only.
- The route is a POST that reads: it is on the route allow-list, needs CSRF and the Origin check, and counts against the api rate limit.
- A user cannot bookmark a filtered view; accepted.
- A response carries no total, so the web page counts exactly only once all pages are loaded.

## Alternatives

- GET with a `sender` query parameter: rejected, the text would be in logs and history.
- Filtering in the browser over all items: rejected, a plan can hold thousands of items and the page loads at most 100 per call.
