---
id: ADR-0031
title: "Web design system: the Paper Trail direction"
status: superseded
area: design-system
tags: [design, tokens, web, paper-trail]
date: 2026-11-10
superseded_by: ADR-0035
guardrails: [guardrail-tailwind, guardrail-a11y]
---

## Context

ADR-0010 asked for a generated design system, proposed as three directions at the first feature with a screen and chosen by Marco. `web-settings` is that feature. Three directions were drawn for the login page, the settings page and their states, in light and dark, at phone and desktop width: Paper Trail, Signal Desk and Pebble. Every text pair in all three passed WCAG 2.2 AA when measured on the rendered page (light and dark).

## Decision

Direction **A, Paper Trail**, chosen by Marco on 2026-11-10: a calm letter from the assistant. Warm paper and ink with a clay accent, a serif display face (Newsreader) with a plain sans for text (Public Sans), small radius, hairline rules, almost still motion. One column of labelled rows with one italic assistant sentence on the settings page. Phone and desktop share one layout.

- The values (palette, type, radius, spacing, motion) come from the approved direction and become `packages/tokens` through `design-tokens-bridge`, in the clickable prototype unit before any production screen. The placeholder tokens are replaced then.
- Semantic token names only; every colour has a light and a dark value; the contrast test of `packages/tokens` covers text pairs at 4.5:1 and borders, focus rings and controls at 3:1.
- New semantic tokens beyond the placeholders: `border`, `divider`, `danger-soft`, `success-soft`, `shadow`, `space-*`, `motion-*`.
- The word list of the interface follows Telegram (C-11 of the spec).

## Consequences

- One layout for 320 px to 1280 px keeps the reflow and 200 % text checks simple (AC-22).
- A later control panel (alert overview) may outgrow the single-column rows; that is then a new decision, not a quiet change of tokens.
- Fonts come from Google Fonts with a system fallback stack; self-hosting them is a follow-up if the CSP or privacy asks for it.

## Alternatives

- B, Signal Desk (cool grey, teal, mono times): fits a future control panel, but is closest to the admin look ADR-0010 wants to avoid.
- C, Pebble (soft cards, pill buttons, speech bubble): most personality, but needs the most space and looks like chat on a page that is not chat.
