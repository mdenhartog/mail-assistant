# syntax=docker/dockerfile:1
# AgentCore Runtime needs linux/arm64 (the CDK app in deploy/aws builds it that way). HTTP agents listen on 8080,
# A2A agents on 9000: set AGENT_PROTOCOL and PORT together (compose.yaml and the CDK app do).
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim@sha256:531f855bda2c73cd6ef67d56b733b357cea384185b3022bd09f05e002cd144ca AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /srv
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY app ./app

FROM python:3.13-slim-bookworm@sha256:a5a7017efc5969e00ae2b91c8eb0631049a569652aa4ffc4501769049ae45c72 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/srv/.venv/bin:$PATH" PORT=8080 AGENT_PROTOCOL=http
# The service never installs packages at run time: pip carries its own copies of msgpack, urllib3 and setuptools, and the
# scanner flags them, so pip goes out of the runtime image.
RUN python -m pip uninstall --yes pip \
    && groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home --home-dir /home/app --shell /usr/sbin/nologin app
WORKDIR /srv
COPY --from=build --chown=app:app /srv /srv
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD ["python", "-m", "app.healthcheck"]
CMD ["python", "-m", "app"]
