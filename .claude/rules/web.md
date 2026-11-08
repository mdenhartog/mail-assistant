---
paths:
  - "apps/web/**"
  - "packages/**"
---

# Web rules (loaded only when working in apps/web or packages)

- Read `apps/web/CLAUDE.md`; load the web guardrails that belong to the file.
- Every component: loading, error, empty and success; keyboard and screen reader work.
- Tokens only; a new value ⇒ a token in `packages/tokens/tokens.json` first.
- Data only through hooks in `src/api/<domain>/*.queries.ts`.
