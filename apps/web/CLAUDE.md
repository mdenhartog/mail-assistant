# Web

- Structure: `src/components`, `src/pages`, `src/hooks`, `src/api/<domain>/{types,api,queries}.ts`, `src/router`.
- Styling only with tokens from `packages/tokens` (no arbitrary values); mobile first, tested on mobile, tablet and desktop.
- Tests: `pnpm test` (Vitest + Testing Library + axe), `pnpm e2e` (Playwright against `docker compose --profile prod-like`; `E2E_BASE_URL` overrides the URL).
- Guardrails: guardrail-typescript, guardrail-react, guardrail-react-router, guardrail-tanstack-query, guardrail-vite, guardrail-tailwind, guardrail-vitest-rtl, guardrail-playwright, guardrail-a11y.
