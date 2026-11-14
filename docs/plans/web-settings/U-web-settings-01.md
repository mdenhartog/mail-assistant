---
intent: INT-002
feature: web-settings
---

# U-web-settings-01: Pebble tokens, self-hosted fonts and contrast test (R1)

- Layer: web
- Contract: `packages/tokens/tokens.json` replaces the placeholder with the Pebble values of the hand-off (colours with a light and dark value: surface, surface-raised, text, text-muted, border, divider, primary, primary-contrast, danger, danger-soft, success, success-soft, focus; radius 999 / 14 / 24 px; soft shadow; spacing and type steps; motion 200 ms press, 250 ms enter, spring curve, removed under reduced motion) through `design-tokens-bridge`. Bricolage Grotesque and Figtree are self-hosted as `woff2` files under `packages/tokens/fonts/` with their OFL licence files (D-2: the CSP blocks Google Fonts); `build.mjs` generates `@font-face` rules with relative URLs and regenerates `tokens.css` and `theme.native.json`. The contrast test covers text pairs at 4.5:1 and border, focus and control pairs at 3:1.
- Files: `packages/tokens/tokens.json`, `packages/tokens/tokens.css` (generated), `packages/tokens/theme.native.json` (generated), `packages/tokens/build.mjs`, `packages/tokens/contrast.test.mjs`, `packages/tokens/fonts/`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-tailwind, guardrail-a11y, guardrail-vite
- Criteria:
  1. Given `tokens.json`, When validated, Then every colour has a light and a dark value, names are semantic and the placeholder description is gone (type: happy; level: unit).
  2. Given text on surface and on surface-raised, text-muted on both, primary-contrast on primary, danger on danger-soft, success on success-soft, in both modes, When measured, Then each pair is at least 4.5:1 (AC-22) (type: a11y; level: unit).
  3. Given border, focus ring and control edge against their adjacent surface in both modes, When measured, Then each is at least 3:1 (AC-23) (type: a11y; level: unit).
  4. Given a token that is 4.49:1 and one that is 4.50:1, When the test runs, Then the first fails naming the pair and the mode, the second passes (type: error; level: unit).
  5. Given a changed `tokens.json` without regenerated files, When `node packages/tokens/build.mjs --check` runs, Then it fails (type: error; level: ci).
  6. Given the motion tokens, When read, Then the longest duration is 250 ms and a reduced-motion value of 0 exists (type: edge; level: unit).
  7. Given the generated CSS, When read, Then every `@font-face` URL is relative, no `https://` URL appears, and every referenced font file exists with a licence file beside it (D-2, AC-14) (type: security; level: unit).
  8. Given `apps/web/src`, When searched for hex colours, `rgb(` and arbitrary Tailwind values, Then there is no hit outside the tokens package (type: edge; level: ci).
