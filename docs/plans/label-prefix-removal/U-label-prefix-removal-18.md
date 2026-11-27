---
intent: INT-010
feature: label-prefix-removal
---

# U-label-prefix-removal-18: Agent re-sort path follows the managed set: build, apply, move back, report

- Component: mail-triage agent
- Layer: backend
- Contract: Found while building unit 03: `usecases/resort_build.py`, `resort_apply.py`, `move_back.py`, `refile_report.py` and `db/pg_resort.py` still import `LABEL_PREFIX`, `OTHER_LABEL` and `assistant_labels`, and call the old `classify` and `file_under`. They take the managed set and the "Other" setting, decide scope by label id and handle labels as ids; a label that is not managed is never added or removed.
- Files: `agents/mail-triage/app/usecases/resort_build.py`, `agents/mail-triage/app/usecases/resort_apply.py`, `agents/mail-triage/app/usecases/move_back.py`, `agents/mail-triage/app/usecases/refile_report.py`, `agents/mail-triage/app/db/pg_resort.py`, tests under `agents/mail-triage/tests/`
- Depends on: U-label-prefix-removal-03, U-label-prefix-removal-04
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest, guardrail-gmail
- Criteria:
  1. Given a re-sort build, When it lists mail, Then only mail of the inbox or a managed label is planned (AC 2, 3). (type: security)
  2. Given an approved plan item, When applied, Then only managed labels are added or removed, by id (AC 3). (type: security)
  3. Given a move back, When it runs, Then it looks at the managed labels only and restores the old pair. (type: happy)
  4. Given mail that carries the archive label and a managed label, When built or applied, Then the archive wins and the mail is left alone. (type: edge)
  5. Given the daily report, When written, Then "Other" is counted by the "Other" setting and the report carries counts only. (type: happy)
  6. Given the source, When searched, Then `OTHER_LABEL`, `LABEL_PREFIX` and `assistant_labels` appear in none of these modules. (type: edge)
  7. Given the existing re-sort tests, When run with the fake Gmail, Then the outcomes are unchanged apart from the label names. (type: edge)
