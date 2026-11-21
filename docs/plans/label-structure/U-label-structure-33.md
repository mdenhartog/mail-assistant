---
intent: INT-008
feature: label-structure
---

# U-label-structure-33: The ingress body limit of the list save fits the v2 list

- Component: platform
- Layer: infra
- Contract: the edge limit for `PUT /api/categories` in the Helm chart (`ingress.categoriesBodyLimitBytes`, 32 768 bytes, set for 50 categories of 500 characters, MC-12) is raised to the 2 MiB that unit 11 chose for the api (a full v2 list with senders is about 1.2 MB), in `values.yaml`, the `values.schema.json` bounds, the README table and the tests that render the ingress; the limit of every other route stays 8 192. Found while building unit 11: without it the edge refuses a v2 list with a 413 before it reaches the api. The chart tests live in `agents/mail-triage/tests/infra` (they render the app chart); this unit lands in the same pull request as units 11 and 34.
- Files: `deploy/charts/app/values.yaml`, `deploy/charts/app/values.schema.json`, `deploy/charts/app/templates/ingress.yaml` (only if the template needs it), `deploy/charts/app/README.md`, `agents/mail-triage/tests/infra/test_categories_route.py` and the other chart tests that name 32 768
- Depends on: U-label-structure-11
- Parallel: yes
- Guardrails: guardrail-helm, guardrail-kubernetes, guardrail-pytest
- Criteria:
  1. Given the default values, When the ingress is rendered, Then the list route has `maxRequestBodyBytes` 2 097 152 and every other route 8 192. (type: happy)
  2. Given `ingress.categoriesBodyLimitBytes` of 0, a negative number, a non-number or above the schema maximum, When the chart is rendered, Then the schema refuses it. (type: error)
  3. Given a value below the api limit, When the chart is rendered, Then it renders (the operator may lower it) and the README says the api limit is 2 MiB. (type: edge)
  4. Given the chart lint and policy checks of the repository, When they run, Then they pass. (type: happy)
