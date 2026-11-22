---
intent: INT-008
feature: label-structure
---

# U-label-structure-35: The ingress body limit of the upload route

- Component: platform
- Layer: infra
- Contract: the Helm chart caps every route at the edge with `ingress.bodyLimitBytes` (8 192 bytes) and only `PUT /api/categories` has its own cap (`ingress.categoriesBodyLimitBytes`, unit 33). The upload route of unit 12 (`POST /api/categories/upload`, an api limit of 320 KiB: the 256 KiB file plus overhead) would be refused with a 413 at the edge. The chart gets a second dedicated route for `POST /api/categories/upload` with its own value `ingress.uploadBodyLimitBytes` (default 393 216, a margin above the api limit; schema bounds from 16 384 to 1 048 576), the README table and the tests that render the ingress; confirm and restore stay on the generic 8 192. This unit lands in the same pull request as unit 12. The chart tests live in `agents/mail-triage/tests/infra`.
- Files: `deploy/charts/app/templates/ingress.yaml`, `deploy/charts/app/values.yaml`, `deploy/charts/app/values.schema.json`, `deploy/charts/app/README.md`, `agents/mail-triage/tests/infra/test_categories_route.py` (or a new test file next to it) and the other chart tests that name the ingress routes
- Depends on: U-label-structure-12
- Parallel: yes
- Guardrails: guardrail-helm, guardrail-kubernetes, guardrail-pytest
- Criteria:
  1. Given the default values, When the ingress is rendered, Then `POST /api/categories/upload` has `maxRequestBodyBytes` 393 216, `PUT /api/categories` 2 097 152 and every other route 8 192. (type: happy)
  2. Given `ingress.uploadBodyLimitBytes` of 0, a negative number, text, 8 192 or above 1 048 576, When the chart is rendered, Then the schema refuses it. (type: error)
  3. Given the confirm and restore routes, When the ingress is rendered, Then they have no dedicated route and keep 8 192. (type: edge)
  4. Given `helm lint --strict` and the chart policy tests of the repository, When they run, Then they pass. (type: happy)
