---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-31: Worker HTTPS egress limited by CIDR

- Component: platform
- Layer: infra
- Release: R2
- Contract: the worker chart HTTPS egress rule allows only the configured pod and service CIDR exceptions (ADR-0049).
- Files: deploy/helm/worker/**, agents/mail-triage/tests/infra/test_worker_https_egress.py, docs/memory/decisions/ADR-0049-*.md
- Depends on: U-mail-categories-22
- Parallel: no
- Guardrails: guardrail-helm, guardrail-kubernetes, guardrail-pytest
- Criteria:
  1. Given the rendered worker chart, Then the HTTPS egress rule carries CIDR exceptions (type: security)
  2. Given no CIDR values, Then rendering fails instead of opening egress (type: error)
