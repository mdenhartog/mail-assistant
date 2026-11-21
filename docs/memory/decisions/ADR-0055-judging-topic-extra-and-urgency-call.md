---
id: ADR-0055
title: "Judging with a topic and an extra label, and a small urgency-only call for sender-rule mail"
status: accepted
area: architecture
tags: [label-structure, mail-triage, llm, prompt-injection, budget]
date: 2026-11-21
supersedes: ADR-0045 (decisions 1 and 3 only; decisions 2, 4, 5 and 6 stay)
guardrails: [guardrail-llm, guardrail-python]
---

## Context

ADR-0045 made the model answer one `category_id` (closed set) next to `urgent`, and said that no second model call is made for urgency (decision 3). INT-008 needs a topic plus at most one extra label (D3), general instructions for the whole list (C-3), and D11: a sender-rule mail in an unticked category still needs an urgency judgement, which cannot come from a category call that was skipped.

## Decision

1. `Judgement` is rebuilt: `topic_id` (an id of the list or the nil id for "Other"), `extra_id` (an id of an extra-label category or null), `urgent`, `reason`, `summary`, `confidence`. Both ids are closed sets. An unknown topic id files under "Other" and drops the extra label; an unknown extra id is dropped; urgency is kept; an invalid answer stays "needs attention". One mail per call.
2. The general instructions and the descriptions are given only as data in separate, fixed places of the prompt, with the limits and escaping of mail text (ADR-0045 decision 2 stays: the urgency rules are fixed in the agent).
3. A new port `UrgencyJudge` with its own prompt and a closed answer: exactly a boolean and a reason of at most 200 characters; anything else is "needs attention"; an answer that names a category is refused. It is called only for a sender-rule mail in an **unticked** category (D11); in a ticked category no call is made.
4. Budget (extends ADR-0021): urgency-only calls, tip calls and plan builds count in the daily model budget with the reserve. When it is used up, a sender-rule mail is still filed and is listed in the daily overview, and no urgency-only call, tip or plan build runs above the reserve.
5. Every filing records the list version used and its source (ADR-0053).

## Consequences

- Reverses decision 3 of ADR-0045 (no second call): one small call exists for one case. The cost is one call per sender-rule mail in an unticked category.
- Rebuild of `Judgement`, `resolve()`, the prompt and the filing record, not a flag.
- Accepted risk AR-1 (a passing sender's text can steer the urgency call) is bounded by the closed answer, the fenced prompt and the daily overview.

## Alternatives

- Give sender-rule mail no urgency at all: breaks D10 (a document or a mail that expects an action must still alert). Rejected.
- Call the full category judgement for sender-rule mail and ignore its category: spends the budget the rule was meant to save. Rejected.
