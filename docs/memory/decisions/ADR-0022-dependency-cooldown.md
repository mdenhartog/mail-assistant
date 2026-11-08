---
id: ADR-0022
title: "Dependency cooldown of 7 days for uv, pnpm and Renovate"
status: accepted
area: security
tags: [supply-chain, uv, pnpm, renovate, dependencies]
date: 2026-11-08
guardrails: [guardrail-python, guardrail-typescript]
---

## Context

The kit's semgrep rules (blocking in CI) require a cooldown for newly published packages in uv, pnpm and Renovate, because a freshly published version can be malicious or unstable. Setting `exclude-newer = "7 days"` did not resolve at first: the lockfiles already hold versions younger than 7 days (for example `fastapi>=0.162.2`).

## Decision

Apply a 7-day cooldown everywhere, with temporary exceptions for the versions that are already locked:

- uv (`backend`, `agents/*`, `mcp-servers/tools`, `channels/chat-gateway`): `exclude-newer = "7 days"` and `[tool.uv.exclude-newer-package]` with the locked packages younger than 7 days, dated 2026-11-08. No locked version changes.
- pnpm (`pnpm-workspace.yaml`): `minimumReleaseAge: 10080`, `trustPolicy: no-downgrade`, `blockExoticSubdeps: true`, and `minimumReleaseAgeExclude` with the exact locked versions younger than 7 days.
- Renovate: `minimumReleaseAge: "7 days"` for all packages; vulnerability alerts have no wait, so a security fix is not delayed.

## Consequences

- A new version is only proposed or resolved 7 days after publication, so a malicious release has time to be found and pulled.
- The exceptions are temporary. From 2026-11-15 the locked versions are older than 7 days: delete both exception lists and run `uv lock` and `pnpm install --frozen-lockfile` to confirm. Until then the excepted packages cannot move to a version published after 2026-11-08.
- Security fixes that are younger than 7 days must be added to an exception list by hand, with the reason in the pull request.

## Alternatives

- Lower the minimum versions in the `pyproject.toml` files to what existed a week ago: could undo recent security fixes. Rejected.
- Turn the three semgrep rules off: no protection against newly published malicious packages. Rejected.
