# syntax=docker/dockerfile:1
# Renovate pins these base images to digests (guardrail-docker).
# Build context: the repository root (docker build -f backend/Dockerfile .), because the backend depends on the shared
# package packages/schedule-policy (a uv path dependency, ../packages/schedule-policy). The directory layout below mirrors
# the repository so that the relative path in pyproject.toml and uv.lock resolves.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /srv/backend
COPY packages/schedule-policy/pyproject.toml /srv/packages/schedule-policy/pyproject.toml
COPY packages/schedule-policy/schedule_policy /srv/packages/schedule-policy/schedule_policy
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY backend/app ./app

FROM python:3.13-slim-bookworm AS runtime
# python:slim-bookworm is Debian and may carry a system /usr/share/zoneinfo, which zoneinfo reads before the `tzdata` wheel.
# PYTHONTZPATH points at a directory that does not exist, so the pinned wheel (uv.lock, ADR-0028) is the only source.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONTZPATH=/nonexistent-zoneinfo PATH="/srv/backend/.venv/bin:$PATH"
# The service never installs packages at run time: pip carries its own copies of msgpack, urllib3 and setuptools, and the
# scanner flags them, so pip goes out of the runtime image.
RUN python -m pip uninstall --yes pip \
    && groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
WORKDIR /srv/backend
# Only the backend directory: schedule_policy is installed into its virtual environment, its sources stay behind.
COPY --from=build --chown=app:app /srv/backend /srv/backend
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status == 200 else 1)"]
CMD ["uvicorn", "app.production:create_production_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-access-log"]
