---
id: ADR-0003
title: Work tracking: repo docs
status: accepted
area: work-tracking
tags: [specs, plans, git]
date: 2026-11-08
guardrails: []
---
## Context
The team needs a home for specs, stories, PRDs, acceptance criteria and plans.

## Decision
All work artefacts live in the Git repository:
- `docs/specs/<feature>.md` — approved specs
- `docs/plans/<feature>.md` — unit plans (phase 4)
- ADRs, threat models and validation evidence in `docs/memory/` and `docs/security/`

Specs are reviewed and approved via GitHub pull requests. Marco is the spec approver.

## Consequences
- Everything is traceable in Git history.
- No external connector (Jira, Confluence, Claude Docs) needed.
- Change this ADR to adopt an external tracker later.

## Alternatives
- Jira Software — rejected: no existing Jira project; overhead not justified for the current team size.
- Claude Docs — rejected: stakeholders are comfortable with GitHub PRs.
