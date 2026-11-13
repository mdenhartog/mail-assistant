# syntax=docker/dockerfile:1
# Build context: repository root (the web app depends on workspace packages).
# Renovate pins these base images to digests (guardrail-docker).
FROM node:24-bookworm-slim@sha256:dc26ae92c9fb15cf6b1d63e20f0944b2efe0f115b20e00be48fb23fceb061c54 AS build
ENV PNPM_HOME=/pnpm PATH="/pnpm:$PATH" CI=1
RUN corepack enable
WORKDIR /repo
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json ./
COPY apps/web/package.json apps/web/
COPY packages/tokens/package.json packages/tokens/
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile --filter web...
COPY packages/tokens packages/tokens
COPY apps/web apps/web
RUN pnpm --filter web exec vite build

FROM nginxinc/nginx-unprivileged:stable-alpine@sha256:f5116ed4606f3eb015dd4a8e28cb9b351476dc0ad4bc6e9f93b19cec130cdf03 AS runtime
# Pick up the Alpine security fixes that are newer than the base image, then drop root again.
USER 0
RUN apk upgrade --no-cache
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/apps/web/dist /usr/share/nginx/html
USER 101
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/"]
