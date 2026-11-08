# Mail Assistant

A personal assistant for Marco's Gmail. The first feature, [mail triage](docs/specs/mail-triage.md), reads incoming mail, files each mail under a category and warns Marco in Telegram only when a mail needs his immediate attention. Nothing is sent without his confirmation and nothing is ever deleted.

Built with the [claude-sdlc-kit](CLAUDE.md): specs, ADRs and plans live in the repository and every change goes through a pull request.

## What is in the repository

| Path | What it is |
| --- | --- |
| [backend/](backend/) | Python + FastAPI API (managed with `uv`) |
| [apps/web/](apps/web/) | Web app: Vite + React + TypeScript + Tailwind, responsive (no native app) |
| [agents/mail-triage/](agents/mail-triage/README.md) | The mail-triage agent |
| [agents/assistant/](agents/assistant/) | Assistant agent |
| [mcp-servers/tools/](mcp-servers/tools/) | MCP tools server |
| [channels/chat-gateway/](channels/chat-gateway/README.md) | Chat channel gateway |
| [packages/tokens/](packages/tokens/) | Shared design tokens |
| [deploy/](deploy/) | Helm charts and environments for Kubernetes (Argo CD) |
| [docs/](docs/) | Specs, designs, plans, ADRs and the API reference |

## Getting started

Requirements: Python with [uv](https://docs.astral.sh/uv/), Node.js with pnpm, and Docker.

```bash
pnpm install
docker compose --profile dev up
```

The `dev` profile starts the API and the web app with live reload. The `prod-like` profile runs the production images locally.

Each agent reads its configuration from the environment and refuses to start when a value is missing. See the README of the component, for example [agents/mail-triage/](agents/mail-triage/README.md). Never put secrets in code, logs or URLs.

## Tests and checks

```bash
cd backend && uv run pytest                      # backend tests
pnpm --filter web test                           # web tests
docker compose --profile prod-like up -d --build --wait
pnpm --filter web e2e                            # end-to-end tests
pnpm run audit                                   # dependency audit
node scripts/docs.mjs check                      # documentation check
```

Run everything with `/sdlc:verify` in Claude Code. See what is being built right now with `node scripts/status.mjs` (writes `docs/STATUS.md`, which is not committed).

## Documentation

- [API reference](docs/api/reference.md), generated from the OpenAPI document. Regenerate it with `node scripts/docs.mjs api`.
- [Specs](docs/specs/), [designs](docs/design/) and [plans](docs/plans/).
- [Decisions (ADRs)](docs/memory/index.md).

## Contributing

Work test-first, never commit on `main`, and open a pull request for every change. The rules are in [CLAUDE.md](CLAUDE.md). Commit messages follow Conventional Commits.
