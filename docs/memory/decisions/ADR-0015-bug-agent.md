---
id: ADR-0015
title: "Bug agent: fix mode"
status: accepted
area: bug-agent
tags: [bug-agent, automation, qa]
date: 2026-11-08
guardrails: []
---
## Context

After each production release, bugs need to be detected, triaged, and optionally fixed automatically.

## Decision

Bug agent mode: **fix**

- Watch window after a release: **48 hours**
- Fix attempts per bug: **3**
- Maximum concurrent open fix PRs: **3**
- Scope: all bugs detected in the watch window that are reproducible as a failing test

The agent will: detect → register in backlog → reproduce as failing test → fix → open a PR. Marco reviews and merges fix PRs.

## Consequences

- Bugs outside the watch window enter the normal backlog.
- Security, identity, payment and GxP code is never auto-fixed (not applicable here, but recorded for completeness).
- The `bug-loop` skill governs the fix cycle.

## Alternatives

- Watch only — rejected: auto-fix reduces mean time to recovery for straightforward bugs.
- Off — rejected: manual triage alone is too slow for a production assistant.
