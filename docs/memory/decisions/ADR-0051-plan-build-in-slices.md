---
id: ADR-0051
title: "The plan build looks at a small number of mails per run and goes on in the next run"
status: accepted
area: operations
tags: [mail-categories, mail-triage, runner, heartbeat, kubernetes]
date: 2026-11-21
guardrails: [guardrail-python, guardrail-kubernetes, guardrail-llm]
---

## Context

ADR-0046 point 3 builds the re-sort plan inside the mail cycle: it judges the mail in scope against the current list, newest first, and pauses only when the daily model budget (above the reserve of ADR-0021) is used up. The first deploy of v0.3.0 showed what that means: at the first start (AC-54) the plan listed about 200 mails and the single run took about eight minutes, and a plan can hold 5 000 mails (hours).

While the build runs, the rest of the mail cycle waits: `deliver` (the Telegram alerts for urgent mail), the overview and the heartbeat all come after it. So urgent alerts come late, and the heartbeat file, which the health check and the liveness probe of the worker chart read (maximum age 180 seconds), goes stale. The compose stack showed `unhealthy`; in Kubernetes the liveness probe would restart the pod in the middle of the build, again and again.

The progress of the build is already stored per mail (the cursor and the counts), and a paused build already continues from the stored cursor.

## Decision

One run of the plan build looks at no more than `BUILD_SLICE` mails (20) and then pauses like it does when the budget is used up. The next mail cycle goes on from the stored cursor. Nothing else about the build changes: newest first, the cap of 5 000, a mail is judged once, the reserve is never spent, a newer list replaces the plan, and "plan ready" is announced once, when the last slice is done.

20 mails take under a minute (about 2 to 3 seconds per judged mail), far below the 180 seconds of the heartbeat. The number is a constant with a constructor parameter so that a test can use a small one; it is not a setting.

## Consequences

- Alerts, the overview and the heartbeat are never kept waiting for more than one slice.
- A plan of N mails takes N / 20 cycles: about 200 mails in ten cycles, a full 5 000 in 250 cycles (several hours at a one-minute interval). The review page already shows "x of about y checked, nothing moves yet".
- The model calls per day do not change; they are spread over more cycles.
- A plan that ends exactly at a slice is ready in that run; a further run does nothing.

## Alternatives

- Touch the heartbeat from inside the build: rejected, it would keep the pod alive but would still delay the alerts.
- Run the build in its own task next to the mail cycle: rejected for now, it adds concurrency (a second writer of the plan, the budget and the Gmail quota) for a gain that slices give more simply.
- Raise the heartbeat age or drop the liveness probe: rejected, the probe is what detects a really stuck agent.
