---
intent: INT-002
feature: web-settings
---

# U-web-settings-02: Backend image with the shared package (R1)

- Layer: infra
- Contract: `backend` depends on `packages/schedule-policy` as a uv path dependency (lockfile updated); `backend/Dockerfile` is built from the repo root, copies the package and sets `PYTHONTZPATH` to the pinned `tzdata` wheel as in the agent image (ADR-0028); compose (`api`, `api-dev`, `api-test`) and the `images` CI job use the repo-root context. No code imports the package yet.
- Files: `backend/pyproject.toml`, `backend/uv.lock`, `backend/Dockerfile`, `backend/Dockerfile.dockerignore`, `compose.yaml`, `.github/workflows/ci.yml`
- Depends on: —
- Parallel: yes
- Guardrails: guardrail-docker, guardrail-compose
- Criteria:
  1. Given a clean `uv sync --frozen` in `backend`, When `import schedule_policy` runs, Then it works (type: happy; level: unit).
  2. Given a docker build from the repo root, When the image starts, Then `from schedule_policy.policy import DEFAULT_POLICY` works (type: happy; level: image).
  3. Given the image, When `zoneinfo` resolves `Pacific/Kiritimati`, Then the data comes from the pinned `tzdata` wheel; a test fails when `/usr/share/zoneinfo` would win (ADR-0028) (type: edge; level: image).
  4. Given the build context, When the image is built, Then `.env`, `.git` and `node_modules` are not in any layer (type: security; level: image).
  5. Given hadolint and Trivy in the `images` job, When run on the new image, Then no warning and no new High or Critical finding (type: security; level: ci).
  6. Given `docker compose --profile dev config` and `--profile test config`, When rendered, Then `api-dev` and `api-test` still resolve, and the existing backend suite and `e2e` job are green (type: happy; level: ci).
