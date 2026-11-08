# Backend

- Layers: `app/routers` (HTTP) → `app/services` (logic) → `app/models` / `app/schemas`; shared dependencies in `app/dependencies.py`.
- Routers are mounted from `discover_routers()` in `app/main.py`; business routes live under `/api`, only the `/healthz` and `/readyz` probes are outside. Every route has an auth dependency (`public` or a role check) and a `response_model` — `tests/test_route_inventory.py` checks this.
- Tests: `uv run pytest` (coverage threshold in `pyproject.toml`); lint: `uv run ruff check . && uv run pyright`.
- Guardrails: guardrail-python, guardrail-fastapi, guardrail-pydantic, guardrail-sqlalchemy-alembic, guardrail-pytest (+ the active optional ones from the root CLAUDE.md).
