# syntax=docker/dockerfile:1
# The mail-triage agent has no inbound port; it polls Gmail and Telegram. Its health check reads /tmp/heartbeat
# (see compose.yaml and deploy/charts/worker). It applies its own database migrations when it starts.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /srv
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY migrations ./migrations

FROM python:3.13-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/srv/.venv/bin:$PATH"
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home --home-dir /home/app --shell /usr/sbin/nologin app
WORKDIR /srv
COPY --from=build --chown=app:app /srv /srv
USER 10001:10001
CMD ["python", "-m", "app"]
