---
intent: INT-008
feature: label-structure
---

# U-label-structure-04: category-policy v2: the YAML schema, the template and the fixtures

- Component: category-policy
- Layer: backend
- Contract: `parse_category_file(bytes) -> ParsedList | Problems` (schema 1: categories with name, kind, description, senders, notify; general instructions; archive label; safe loading with the event-stream check of ADR-0058 but no HTTP), `dump_category_file(list) -> bytes` (the export), the template and example files, and the fixtures (valid, the anonymised 43-label golden file, hostile files).
- Files: `packages/category-policy/category_policy/yaml_file.py`, `packages/category-policy/template/mail-categories.template.yaml`, `packages/category-policy/template/mail-categories.example.yaml`, `packages/category-policy/tests/fixtures/` (valid, golden, hostile), tests
- Depends on: U-label-structure-02, U-label-structure-03
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pydantic, guardrail-pytest
- Criteria:
  1. Given a valid file, When parsed, Then the list equals the expected one and dumping it and parsing again gives the same list. (type: happy)
  2. Given a file that is over 256 KiB, has an anchor, an alias, a merge key, an object tag, duplicate keys, unknown fields, depth 1000, a BOM, tabs or a NUL byte, When parsed, Then every problem is returned with line and field (`line 12, senders[3]`) and nothing is built. (type: security)
  3. Given a scalar `no`, `on` or `yes` as a name or sender, When parsed, Then it stays a string or is refused, never a boolean. (type: edge)
  4. Given the anonymised 43-label golden file, When parsed, Then it passes and equals the list of conversion choices the user signed off (names, kinds, descriptions, senders, general instructions, each place where meaning was lost). (type: happy)
  5. Given the template and the example file, When parsed, Then both pass and every field of the format is explained in comments. (type: happy)
  6. Given a problem, When it is reported, Then the message names the field and place and never the value. (type: security)
