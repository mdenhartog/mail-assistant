## What and why
<!-- one paragraph; link to the spec -->
Intent: `docs/intent/INT-…` · Spec: `docs/specs/…` · Plan: `docs/plans/…` · Review record: `docs/reviews/…`

## Decisions
<!-- ADRs this PR follows or adds (docs/memory/decisions/…) -->

## Threat-model delta
<!-- new/changed threats and mitigations, or "no change to trust boundaries" with the reason -->

## Units in this PR
| Unit | Criteria | Tests | Status |
|---|---|---|---|

## Test evidence
- [ ] Tests demonstrably red first, then green (see commits `test:` → `feat:`)
- [ ] Backend: ruff, pyright, bandit, pytest (coverage ≥ 90 %)
- [ ] Web/mobile: eslint, tsc, vitest (coverage ≥ 90 %), knip, `pnpm run audit`
- [ ] E2E: Playwright mobile/tablet/desktop + axe; Maestro (for mobile)
- [ ] GxP-relevant: GAMP 5 scenarios executed, evidence package attached (`validation/packages/…`)

## Screenshots
| Mobile | Tablet | Desktop |
|---|---|---|

## Challenge (red vs blue)
<!-- summary of red-team / security-reviewer / code-reviewer; no open Critical/High -->

## Cleanup gate
<!-- report: dead code, complexity, duplication, ASSUMPTION markers, memory budget -->
