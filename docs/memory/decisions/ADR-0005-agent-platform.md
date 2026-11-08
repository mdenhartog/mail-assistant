---
id: ADR-0005
title: Agent platform self with telegram
status: accepted
date: 2026-11-08
area: agent-platform
tags: [agents,mcp,a2a]
---
## Decision
Agents, MCP servers and channel gateways are separate containers (agents/, mcp-servers/, channels/), registered in .sdlc/components.json.
Platform: **self**. They run on Docker Desktop and Kubernetes (deploy/charts/component); models through Amazon Bedrock unless build_model is changed.
## Consequences
Libraries are resolved to their latest compatible versions when a component is created; move them later with `node scripts/components.mjs upgrade`. Changing platform is a new ADR that supersedes this one.
