---
id: ADR-0001
title: "Development process: claude-sdlc-kit"
status: accepted
area: process
tags: [sdlc, tdd, security]
date: 2026-11-08
guardrails: []
---

## Context

The project is built with Claude Code and must be test-driven, secure by design and maintainable, with decisions that are recorded and easy to find.

## Decision

We follow the SDLC of the claude-sdlc-kit (plugin `sdlc`, version 0.3.0): spec → threat model → design → (optional) prototype → units → TDD → challenge → verify → PR → release, with the guardrails listed in the root CLAUDE.md. All artefacts are written in English.

## Consequences

- Every feature has a spec, threat model and plan in `docs/`.
- Hooks enforce TDD, branch-based work and dependency guardrails.
- Deviating from a phase or guardrail requires a new ADR.

## Alternatives

- Ad-hoc work with loose prompts — rejected: not repeatable, no assurance of security and tests.
