---
id: ADR-0016
title: "Process autonomy: fixed gates only"
status: accepted
area: process
tags: [autonomy, gates, approval]
date: 2026-11-08
guardrails: []
---
## Context
The team must decide where Claude must pause for human approval, beyond the kit's default fixed gates.

## Decision
Claude operates autonomously within phases and pauses **only at the fixed gates**:
1. Spec approval (after phase 1–2)
2. Threat model review (after phase 2)
3. Design / ADR review (after phase 3)
4. Pull request review and merge (after phase 7–8)

No additional stops are added for external API calls or infrastructure changes at this time.

## Consequences
- Faster iteration within a feature.
- If an unexpected external API change or infrastructure incident warrants extra oversight, this ADR is superseded.

## Alternatives
- Also before external API calls — rejected: slows iteration without adding meaningful safety at this team size.
- Also before infrastructure changes — deferred: may be revisited when a production cluster is provisioned.
