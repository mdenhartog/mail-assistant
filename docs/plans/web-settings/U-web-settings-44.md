---
intent: INT-002
feature: web-settings
---

# U-web-settings-44: Mutation workflow wiring for the pure security modules (R1; release gate)

- Layer: infra
- Contract: ADR-0030 item 4 extended to the backend: `backend/cosmic-ray.toml` lists every module that carries the marker `# pure module (mutation-gated)` (U-10, U-11, U-24: `code_hash.py`, `mask.py`, `digest.py`, `return_to.py`, `code_rules.py`, `expiry.py`, `limits.py`, `clientaddr.py`), with annotations excluded; `.github/workflows/mutation.yml` gets a `backend` job like the others (schedule and manual start, fails below 85 %). The baseline gate already ran per unit; this unit only wires the schedule.
- Files: `backend/cosmic-ray.toml`, `.github/workflows/mutation.yml`, `backend/pyproject.toml`, `backend/uv.lock`, `backend/tests/test_mutation_config.py`
- Depends on: U-web-settings-10, U-web-settings-11, U-web-settings-24
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest
- Criteria:
  1. Given `mutation.yml`, When read, Then a `backend` job triggers on `schedule` and `workflow_dispatch`, runs cosmic-ray and fails when more than 15 % of mutants survive (ADR-0030) (type: happy; level: ci).
  2. Given `cosmic-ray.toml`, When compared with the modules that carry the marker, Then the lists are equal; a new marked module without an entry, or an entry for a module that is gone, fails (the config cannot go stale) (type: security; level: unit).
  3. Given the config, When read, Then annotations are excluded from mutation (type: happy; level: unit).
  4. Given each listed module, When its imports are read, Then none imports FastAPI, SQLAlchemy or the network (type: edge; level: unit).
  5. Given the first manual run, When it finishes, Then its score and survivors are recorded under "Changes made during the build" with the committed exclusion lists, each survivor killed or listed with a reason (type: happy; level: ci).
