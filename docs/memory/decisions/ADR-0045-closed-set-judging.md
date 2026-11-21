---
id: ADR-0045
title: "Judging against the user's list: closed set, urgency separate, security mail pinned"
status: accepted
partly_superseded_by: ADR-0055 (decisions 1 and 3)
area: architecture
tags: [mail-categories, mail-triage, llm, prompt-injection]
date: 2026-11-14
guardrails: [guardrail-llm, guardrail-python]
---

## Context

`mail-triage` decision D1 (the agent chooses the categories) and C2 (at most 15) are reversed by INT-004. Today category and urgency come from one model call (`Judgement` in `agents/mail-triage/app/core/judgement.py`); descriptions written by the user would enter that prompt and could move the urgency (MC-1, MC-2, MC-19).

## Decision

1. `Judgement` is rebuilt: the answer holds `category_id` (an id of the current list, a closed set) next to `urgent`; there is no free category name. One mail per call.
2. The urgency rules are fixed in the agent's system prompt. Descriptions are given only in a separate data block, with the limits and escaping of mail text. The urgency never depends on the list.
3. An unknown or invalid category id goes to "Other" and keeps the model's urgency; an invalid answer stays "needs attention". No second model call is made for urgency.
4. The agent never files the app's own sign-in code mail or Google security mail: verified sender means `Authentication-Results` shows DMARC pass for a From domain on a configured allow-list. That mail also never becomes a plan item.
5. Every filing records the list version it used.
6. The agent seeds list version 1 from its current labels (C-1); until then the api answers "not ready".

## Consequences

- Reverses D1 and C2 of `mail-triage`, drops `MAX_CATEGORIES`, and records accepted risks MR-2 (a wrong category) and MR-3 (descriptions go to the Anthropic API; extends A-1 of ADR-0018).
- A rebuild of `Judgement`, `resolve()` and the prompt, not a flag (rebuild-not-patch).
- A configured allow-list of security sender domains.

## Alternatives

- A second model call for urgency: doubles the budget. Rejected.
- Let the model decide the pinning: an injected description could undo it. Rejected.
