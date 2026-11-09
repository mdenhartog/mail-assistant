# syntax=docker/dockerfile:1
# The mail-triage agent has no inbound port; it polls Gmail and Telegram. Its health check reads /tmp/heartbeat
# (see compose.yaml and deploy/charts/worker). It does not migrate when it starts: `python -m app migrate` is a separate
# one-shot job with the owner role (ADR-0025).
# Build context: the repository root (docker build -f agents/mail-triage/Dockerfile .), because the agent depends on the
# shared package packages/schedule-policy (a uv path dependency, ../../packages/schedule-policy). The directory layout
# below mirrors the repository so that the relative path in pyproject.toml and uv.lock resolves.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /srv/agents/mail-triage
COPY packages/schedule-policy/pyproject.toml /srv/packages/schedule-policy/pyproject.toml
COPY packages/schedule-policy/schedule_policy /srv/packages/schedule-policy/schedule_policy
COPY agents/mail-triage/pyproject.toml agents/mail-triage/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY agents/mail-triage/app ./app
COPY agents/mail-triage/migrations ./migrations

FROM python:3.13-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/srv/agents/mail-triage/.venv/bin:$PATH"
# The agent never installs packages at run time: pip carries its own copies of msgpack, urllib3 and setuptools, and the
# scanner flags them, so pip goes out of the runtime image.
RUN python -m pip uninstall --yes pip \
    && groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home --home-dir /home/app --shell /usr/sbin/nologin app
WORKDIR /srv/agents/mail-triage
# Only the agent directory: schedule_policy is installed into its virtual environment, its sources stay behind.
COPY --from=build --chown=app:app /srv/agents/mail-triage /srv/agents/mail-triage
USER 10001:10001
CMD ["python", "-m", "app"]
