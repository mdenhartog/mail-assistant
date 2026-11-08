---
id: ADR-0011
title: API integrations: Gmail and Google Calendar
status: accepted
area: api-style
tags: [gmail, google-calendar, rest, oauth2]
date: 2026-11-08
guardrails: [guardrail-gmail, guardrail-google-calendar]
---
## Context
The mail assistant must read and send email, manage labels/threads, and interact with calendar events.

## Decision
Two Google API integrations:

### Gmail API
- Direction: we call it
- Interface: REST (Google API Client Library for Python)
- Auth: Google OAuth2, scopes `gmail.readonly`, `gmail.send`, `gmail.modify` (labels, threads)
- Environment: Google Cloud (internet)
- Data classification: personal email content — confidential; never logged in full

### Google Calendar API
- Direction: we call it
- Interface: REST (Google API Client Library for Python)
- Auth: shared OAuth2 token (same consent as Gmail)
- Scopes: `calendar.readonly`, `calendar.events`
- Environment: Google Cloud (internet)
- Data classification: personal calendar data — confidential; never logged in full

Both guardrails (`guardrail-gmail`, `guardrail-google-calendar`) must be loaded when touching integration code.

## Consequences
- The first feature that uses either API runs through `api-integration` (contract first, both sides secured).
- Refresh tokens must be stored encrypted; access tokens in memory only.
- Quota limits and retry strategies are defined in each guardrail.

## Alternatives
- Microsoft Graph (Outlook) — deferred: no Outlook integration in scope yet.
