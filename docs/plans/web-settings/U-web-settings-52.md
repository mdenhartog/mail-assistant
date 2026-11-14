---
intent: INT-002
feature: web-settings
---

# U-web-settings-52: Chart sets the trusted proxies; production refuses an empty list (R1; challenge fix; RT-02, SEC-01)

- Layer: infra, backend
- Contract: the api Deployment renders `APP_TRUSTED_PROXY_CIDRS` and `APP_TRUSTED_PROXY_HOPS` from `api.config.trustedProxyCidrs` and `trustedProxyHops`; `values.schema.json` requires them when `ingress.enabled`; `validate_startup` refuses an empty CIDR list when the environment is production.
- Files: `deploy/charts/app/templates/workloads.yaml`, `deploy/charts/app/values.yaml`, `deploy/charts/app/values.schema.json`, `deploy/envs/local/values.yaml`, `backend/app/startup.py`, `backend/tests/test_startup.py`, `backend/tests/test_chart_env.py`
- Depends on: U-web-settings-41
- Parallel: yes
- Guardrails: guardrail-helm, guardrail-kubernetes, guardrail-fastapi
- Criteria:
  1. Given the chart rendered with the local values, When the api env is read, Then both variables are present and the CIDR list is valid and non-empty (W-7, W-17) (type: security; level: chart).
  2. Given ingress enabled and no CIDR list, When the schema runs, Then it refuses (type: error; level: chart).
  3. Given environment production and an empty list, When the api starts, Then it exits non-zero naming the setting (type: security; level: unit).
  4. Given the chart env names, When compared with `Settings`, Then every name exists (existing test extended) (type: edge; level: unit).
