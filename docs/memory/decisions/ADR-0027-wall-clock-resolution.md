---
id: ADR-0027
title: "Wall-clock times: resolution of non-existent and ambiguous local times"
status: accepted
area: architecture
tags: [mail-triage, time, dst]
date: 2026-11-09
guardrails: [guardrail-python]
---

## Context

`time_policy` builds times with the local zone and compares wall-clock values. Once the zone and the times are settings, a configured time can fall in a clock-change gap or occur twice, and results then depend on how `zoneinfo` resolves them (round table, 2026-11-09).

## Decision

All scheduling compares UTC moments, and due moments are stored in UTC. A configured wall time that does not exist on a day resolves to the first valid moment after the gap (02:30 becomes 03:00). A time that occurs twice resolves to its first occurrence. A quiet window length is validated in clock minutes (1 to 12 hours), not in elapsed time.

## Consequences

- One rule in `TimePolicy`, covered by table tests for Europe/Amsterdam, America/New_York (other change dates) and a zone with a change at midnight.
- On a 23 h or 25 h day a window can last 1 hour more or less in real time.

## Alternatives

- RFC 5545 rule (apply the offset before the gap, so 02:30 becomes 03:30): an hour late for an overview; rejected.
- Elapsed-time window length: would make validation depend on the date; rejected.
