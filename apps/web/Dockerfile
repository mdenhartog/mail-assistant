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
# The base image ships four nginx modules (xslt, geoip, image-filter, njs) that this app never loads (no `load_module`).
# They pin nginx to its exact version, so a plain `apk upgrade` cannot move nginx, and the xslt module is the only
# reason libxml2 is there. Removing them lets nginx itself be upgraded and drops that code from the image.
# The nginx version is left unpinned on purpose: the base image already pins nginx to one version, and that pin is
# what has to move whenever Alpine ships a security fix (the base image itself is pinned by digest).
USER 0
# hadolint ignore=DL3018
RUN apk del --no-cache nginx-module-xslt nginx-module-geoip nginx-module-image-filter nginx-module-njs \
    && apk add --no-cache --upgrade nginx \
    && apk upgrade --no-cache
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY apps/web/snippets/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=build /repo/apps/web/dist /usr/share/nginx/html
USER 101
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/"]
