# Intent

One file per intent, `INT-nnn-<slug>.md`, written by the originator in their own words — the first link of the artefact chain (intent → spec → plan → code + tests → review record → production signal → new intent). Claude may help complete the template but never rewrites the intent. Create one with `/sdlc:intent` (skill `intent`): it takes the next id, asks for what is missing, checks completeness with questions, and only the originator confirms.

```markdown
---
id: INT-001
title: Short name of the intent (max 8 words)
originator: <name or role>
status: draft          # draft → confirmed (only the originator confirms)
date: YYYY-MM-DD
signal: SIG-nnn        # only when a production signal or the bug agent triggered it
---
## What I want
## Why (the problem, who has it, how often)
## How I will know it works
## What it must not do
## Open questions    # optional: questions for the spec phase, never answers
## Original wording  # optional: your own text in your language, kept as written
```
