---
paths:
  - "backend/**"
---

# Backend rules (loaded only when working in backend/)

- Read `backend/CLAUDE.md` and load the backend guardrails that belong to the file.
- New route: auth dependency + `response_model` + tests for every error status.
- Model change: an Alembic migration with a working `downgrade()` in the same unit.
- New dependency: check licence and maintenance; the dependency-watch hook reports missing guardrails.
