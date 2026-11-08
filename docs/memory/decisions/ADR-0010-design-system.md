---
id: ADR-0010
title: "Design system: generate modern AI-first style"
status: accepted
area: design-system
tags: [design, tokens, tailwind, ui]
date: 2026-11-08
guardrails: [guardrail-tailwind]
---

## Context

The mail assistant needs a deliberate visual identity. The style must be generated rather than imported from an existing brand.

## Decision

Generate a new design style with the following brief:

- **Character**: Modern & assistant-like (AI-first tool) — conversational UI, prominent AI suggestions, chat-like interaction panels. Feels like a smart assistant rather than a classic email client.
- **Theme**: Light + dark mode (system-preference-driven via Tailwind `dark:` variant)
- **Accessibility**: WCAG 2.2 AA minimum contrast across all themes
- **Language**: English only (no i18n at this stage)
- **Process**: `ui-ux-pro-max` proposes three directions at the first feature's phase 3; the user picks one; `design-tokens-bridge` converts it to `packages/tokens`

Styles to avoid: cluttered dashboards, heavy gradients, neon gamification, generic "bootstrap blue" SaaS look.

## Consequences

- `packages/tokens` will hold the final design tokens (colours, typography, spacing, radius).
- Design decisions are recorded per feature when the first screen is built.
- The `guardrail-tailwind` anti-generic-AI rules apply; any deliberate override requires a new ADR.

## Alternatives

- Existing brand — rejected: no brand assets provided.
- Claude Design system — not available; user does not have an existing Claude Design artifact.
