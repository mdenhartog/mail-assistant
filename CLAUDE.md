# Mail Assistant

Built with the claude-sdlc-kit. Always work through the skill `sdlc-flow` — start a feature with `/sdlc:feature <name>`.

## Language
All project artefacts are written in English: code, comments, docs, specs, ADRs, test scenarios, validation evidence, commit messages and PRs.

## Stack
- Backend: Python + FastAPI (uv) — `backend/`
- Web: Vite + React + TypeScript + Tailwind — `apps/web/`
- Mobile: no native app; responsive web
- Shared: `packages/tokens` (design tokens)
- Local: `docker compose --profile dev up` · production: Kubernetes via Helm + Argo CD (`deploy/`)

## Active guardrails
guardrail-python, guardrail-fastapi, guardrail-pydantic, guardrail-sqlalchemy-alembic, guardrail-pytest, guardrail-typescript, guardrail-react, guardrail-react-router, guardrail-tanstack-query, guardrail-vite, guardrail-tailwind, guardrail-vitest-rtl, guardrail-playwright, guardrail-a11y, guardrail-tls-certificates, guardrail-docker, guardrail-compose, guardrail-kubernetes, guardrail-helm, guardrail-mcp-server, guardrail-strands-agents, guardrail-agent-memory, guardrail-rag, guardrail-a2a, guardrail-llm, guardrail-telegram, guardrail-oauth2-oidc, guardrail-gmail, guardrail-google-calendar

Load a guardrail only when you touch code of that type. New language/framework/system: `/sdlc:add-guardrail <name>`.

## Memory
- Decisions and knowledge live in `docs/memory/` (skill `app-memory`): read `docs/memory/index.md` first, then only the 1–3 relevant items.
- This file stays ≤ 60 lines; details belong in `docs/memory/` or in a folder's own `CLAUDE.md`.

## Hard rules
1. TDD: a failing test first (the TDD-guard hook enforces this).
2. Contract or behaviour changes ⇒ `rebuild-not-patch`, no flags or bolted-on parameters.
3. A choice without an ADR ⇒ `decision-gate`; never choose silently.
4. Secure by design; no secrets in code, logs or URLs.
5. Never commit on `main`; one worktree per unit (`git-workflow`).

## Commands
- Backend tests: `cd backend && uv run pytest`
- Web tests: `pnpm --filter web test`
- E2E: `docker compose --profile prod-like up -d --build --wait`, then `pnpm --filter web e2e`
- Dependency audit: `pnpm run audit`
- Check everything: `/sdlc:verify`
