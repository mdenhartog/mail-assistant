# Backend

- Layers: `app/routers` (HTTP) → `app/services` (logic) → `app/models` / `app/schemas`; shared dependencies in `app/dependencies.py`.
- Routers are mounted from `discover_routers()` in `app/main.py`; every route path is on the exact allow-list `ROUTE_ALLOW_LIST` in `app/core/security.py`, declares `public` or `session` and has a `response_model` — `tests/test_route_inventory.py` checks this. Errors are generic `application/problem+json` (`app/errors.py`); `app/middleware.py` adds the headers and request id; routes that need a limit declare `Depends(limit("bucket"))` (`app/limit_guard.py`).
- Tests: `uv run pytest` (coverage threshold in `pyproject.toml`); lint: `uv run ruff check . && uv run pyright`.
- Guardrails: guardrail-python, guardrail-fastapi, guardrail-pydantic, guardrail-sqlalchemy-alembic, guardrail-pytest (+ the active optional ones from the root CLAUDE.md).
