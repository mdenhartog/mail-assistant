---
id: ADR-0028
title: "Time-zone lookup: a hand-curated list of cities, countries and aliases"
status: accepted
area: architecture
tags: [mail-triage, time-zone, data]
date: 2026-11-09
guardrails: [guardrail-python]
---

## Context

Marco types a city or a country to choose a time zone (spec `adjustable-quiet-hours`, C-6). Something must map names to IANA zones, offline and deterministically.

## Decision

A small data file maintained in the repository, in the shared package `packages/schedule-policy`: a few hundred large cities and all countries, each with its IANA zone (several for large countries) and aliases ("NYC", "Wien", "Den Haag"). Matching ignores case and accents. Marco asks for missing places to be added; each addition is a test row. A guard test checks that every listed zone exists in the pinned `tzdata`.

## Consequences

- No new licence, no network call, no extra dependency; behaviour is fully under our control.
- A place that is not listed gives "nothing found" (AC-17) until it is added; the typed IANA name (`Europe/Paris`) is a fallback.
- The list is part of the shared package, so the web combobox in `web-settings` uses the same data.

## Alternatives

- GeoNames cities of 15,000 inhabitants or more (CC BY 4.0): best coverage, but needs attribution and a yearly refresh; not chosen by Marco.
- Only IANA zone names and the tzdata country table: about 400 cities, no curation, but small places fail; not chosen by Marco.
