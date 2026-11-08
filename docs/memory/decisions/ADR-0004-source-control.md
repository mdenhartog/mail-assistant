---
id: ADR-0004
title: "Source control: GitHub"
status: accepted
area: source-control
tags: [github, ci, releases]
date: 2026-11-08
guardrails: []
---
## Context
The project needs a source control host, CI pipeline, PR workflow, and a release process.

## Decision
- Host: **GitHub** — repository `mdenhartog/mail-assistant`
- CI: GitHub Actions (`./github/workflows/ci.yml`, `release.yml`)
- Branch protection: `main` is protected; at least one approving review required (Marco)
- Release: release-please + GHCR; cosign keyless signing
- Merge queue enabled; direct pushes to `main` are blocked

## Consequences
- The kit's plugin marketplace is reachable from GitHub natively.
- Renovate handles dependency updates via PRs.
- Change this ADR to migrate to Bitbucket.

## Alternatives
- Bitbucket Cloud / Data Center — rejected: team already uses GitHub; no migration benefit.
