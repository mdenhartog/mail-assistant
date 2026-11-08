# Review records

One file per feature, `<feature>.md`, written in phases 6–9: the durable record of how the change was reviewed, approved and deployed — part of the audit trail.

```markdown
---
intent: INT-nnn
spec: docs/specs/<feature>.md
plan: docs/plans/<feature>.md
pr: <url>
release: <version / image digest>
---
## Gates                (phase → result → evidence link)
## Challenge             (red-team / code-reviewer / security-reviewer / cso findings and their resolution)
## Approvals             (who approved what, when: spec, design, merge, production; QA for GxP)
## Deploy                (staging, production, rollback plan)
## Validation package    (GxP only: run id, package path, verification result)
```
