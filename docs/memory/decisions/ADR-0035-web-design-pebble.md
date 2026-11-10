---
id: ADR-0035
title: "Web design system: the Pebble direction"
status: accepted
area: design-system
tags: [design, tokens, web, pebble]
date: 2026-11-10
supersedes: ADR-0031
guardrails: [guardrail-tailwind, guardrail-a11y]
---

## Context

ADR-0031 chose the Paper Trail direction on 2026-11-10. The same day, after the design was merged, Marco asked for the **Pebble** theme instead. Three directions had been drawn for the login page, the settings page and their states, in light and dark, at phone and desktop width; the text pairs of all three passed WCAG 2.2 AA when measured on the rendered page.

## Decision

Direction **C, Pebble**, chosen by Marco: a friendly companion with soft edges. Blush and berry (rendered starting values: surface `#FAF1EE`, primary `#8A2F63`, text `#2A1823`), Bricolage Grotesque for headings with Figtree for text, radii of 14 px (controls) and 24 px (cards, bubble), pill buttons, one soft card per setting (a 2 by 2 grid on desktop, stacked on a phone), a soft shadow, and a short spring motion (about 200 ms).

- The values (palette, type, radius, spacing, shadow, motion) become `packages/tokens` through `design-tokens-bridge` in the prototype unit, before any production screen. The placeholder tokens are replaced then, with semantic names and a light and a dark value for each colour.
- The contrast test of `packages/tokens` covers text pairs at 4.5:1 and borders, focus rings and controls at 3:1, and runs in CI.
- **Deliberate exception to `guardrail-tailwind`.** The guardrail forbids a chat-bubble layout for non-chat features unless the design system chooses it deliberately. ADR-0010 asks for a conversational, assistant-like character, and Pebble is chosen on purpose. The exception is limited: one short greeting from the assistant at the top of the settings page, which carries no control and is not a chat layout. Nothing else on the page is a bubble.
- Shadows stay soft and small; no glassmorphism, no gradient hero, no emoji as icons.
- The word list follows Telegram (C-11 of the spec).

## Consequences

- More vertical space than a single column of rows: four cards plus banners need more scrolling on a phone. The prototype checks 320 px and 200 % text size; if a card layout fails AC-22 the layout changes, not the checks.
- The pill buttons in the confirmation dialog (R2) need an extra check that the destructive button is visibly different from the safe one without colour alone.
- More tokens (two radii, shadow, spring motion) to maintain than a hairline design.
- Fonts come from Google Fonts with a system fallback stack; self-hosting is a follow-up if the content security policy or privacy asks for it.

## Alternatives

- A, Paper Trail (ADR-0031, superseded): calmer and cheaper to keep accessible; replaced at Marco's request.
- B, Signal Desk: fits a future control panel; closest to the admin look ADR-0010 wants to avoid.
