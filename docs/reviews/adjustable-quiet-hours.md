---
intent: INT-002
spec: docs/specs/adjustable-quiet-hours.md
plan: docs/plans/adjustable-quiet-hours.md
pr: https://github.com/mdenhartog/mail-assistant/pull/15
release: not released yet
---

# Review record: adjustable quiet hours (Telegram)

The units were merged through pull requests #16 to #46 (list below); the intent, specs, threat models, design and plan came in with #15. The web side is the separate feature `web-settings`.

## Gates

| Phase | Result | Evidence |
| --- | --- | --- |
| 1 Spec | Approved by Marco, 2026-11-09 | `docs/specs/adjustable-quiet-hours.md` front matter, PR #15 |
| 2 Threat model | Written, mitigations traced to tests | `docs/security/adjustable-quiet-hours-threat-model.md` |
| 3 Design | ADR-0023 to ADR-0028 | `docs/memory/index.md` |
| 4 Plan | 43 units, then 16a to 16f from the challenge round | `docs/plans/adjustable-quiet-hours.md` |
| 5 Build, test first | 43 units merged, one pull request each (#16 to #34), plus the fix units #37, #40 to #46 | `gh pr list --state merged`, trailers `Unit: U-quiet-hours-nn` on every commit |
| 6 Challenge | Red-team, code review and security review; every valid finding fixed or accepted below | this file, section Challenge |
| 7 Verify | Component checks green, all hooks green, CI green on main (e11c48d), mutation scores met | see below |
| 8 Finish | Documentation in the pull request `docs/INT-002/adjustable-quiet-hours-docs` | `node scripts/docs.mjs check` |
| 9 and 10 Release and learn | Not done yet | |

### Verify evidence (main at e11c48d)

- `node scripts/components.mjs check`: 4 components passed; mail-triage 1075 passed, 2 skipped (two cases of the shared contract fixture whose malformed times cannot be stored as minutes in the database; `test_settings_store.py` skips them on purpose); coverage 98.7 % against the 90 % gate.
- `pre-commit run --all-files`: all hooks passed (ruff, pyright, bandit, gitleaks, semgrep, hadolint, markdownlint); only `no-commit-to-branch` fails when run on main, which is expected.
- `pip-audit` for mail-triage: no known vulnerabilities. The local package `schedule-policy` cannot be audited from PyPI by hand; its own CI job runs `pip-audit`.
- CI on main: `backend`, `components` (includes the Trivy scan of the image, no ignores), `images`, `helm`, `helm-worker`, `e2e`, `runtime-role`, `schedule-policy`, `security`, `web`, `docs` all green; `gxp` is skipped because the system is not GxP (ADR-0006).
- `runtime-role` job: the migrate job runs against the prod-like database, then 19 forbidden statements as the runtime role must fail with SQLSTATE 42501 and the allowed paths must work.
- Mutation testing (workflow `mutation.yml`, CI on Linux with CPython 3.14.4): first run 42865370873 on main gave `schedule_policy` 86.93 % and `app/core/time_policy.py` 89.83 % killed (criteria U-01 #10 and U-03 #11, both 85 %). Marco asked for a margin of at least 5 points, so units 16g and 16h added tests for every survivor that a behavioural test can kill. Result in CI on main (run 42883754433): `schedule_policy` 90.15 % and `time_policy.py` 90.40 % killed. The remaining survivors are equivalent mutants. About 30 of them replace `|` in a type annotation; CPython 3.14 evaluates annotations lazily (PEP 649), so on CI such a mutant changes nothing, while on 3.13 it fails at import and counts as killed (local scores were about 6 points higher). The score was not raised by excluding operators or by reshaping production code.
- Not run locally: the end-to-end suite against a local Docker stack (it would use the developer's own stack; CI runs the same prod-like stack) and a live run against real Gmail, Telegram and Anthropic (manual run in `docs/reviews/mail-triage-e2e.md`).

## Challenge

Three independent reviewers worked in parallel and read-only: `red-team` (with reproducing scratch tests), `code-reviewer` and `security-architect`. No blockers; 5 + 6 + 7 findings. Merged by the moderator into the units 16a to 16f (ADR-0030).

| Finding | Source | Resolution |
| --- | --- | --- |
| Runtime role could update and delete the mail audit trail and other tables | security 1, red-team 3 | Fixed in 16a (#44): per-table grants, `audit_log` and `overview_log` append-only |
| Writer chose its own channel, actor and version | security 4, red-team 3 | Fixed in 16a: guard trigger (version must rise by one, channel from `session_user`, `db_role` stored) |
| Runtime password sent in clear SQL, `?ssl=` of the owner URL dropped | security 2, red-team 2 | Fixed in 16b (#42): SCRAM-SHA-256 verifier computed in the job, TLS parameters passed on, `NOREPLICATION NOBYPASSRLS`, role memberships fail the job |
| `app.consent` still migrated with the worker URL | security 5 | Fixed in 16b: it checks the schema and names the migrate job |
| `/settings` silent when the stored row is invalid | red-team 1 | Fixed in 16c (#43): card with the values in use and a note; a valid answer overwrites the row |
| `PgStore` used its own clock | code review 2 | Fixed in 16c: one shared `ConversationStore` |
| Stale docstring, dead `is_movable`, duplicate `_hhmm`, unused `httpx2` | code review 3 to 5, security 6 | Fixed in 16c |
| Replayed Telegram update after a restart | red-team 5 | Fixed in 16d (#46): last update id stored in `poll_state.telegram_update_id` |
| Migrate NetworkPolicy not present while the Job runs, Job shared the default ServiceAccount, README used `--from-literal` | red-team 4, security 7 | Fixed in 16e (#40) |
| System tzdata could win over the pinned package | red-team lead | Fixed in 16e: `PYTHONTZPATH` in the runtime image |
| Shared package never tested or audited in CI | security 3 | Fixed in 16f (#41); the new job also found that `validate` accepted `localtime` on Linux, fixed in the same pull request |
| 85 % mutation gate not enforced in CI | code review 1 | Fixed in 16f: nightly and manual `mutation.yml` |
| CI tool images pinned by tag, not digest | security 6 | Accepted: follow-up through Renovate (`pinDigests`) |
| Zone CHECK only a pattern | red-team 1 | Accepted: an invalid zone can now be repaired from `/settings` |
| Each of two pull requests green, main red after both merged (16a and 16c) | found during merge | Fixed in #45 (tests bumped the version); lesson: pull requests that touch the same tests merge one at a time, with main merged in |
| Update id stored after handling, not in the same transaction | 16d builder | Accepted: a crash between the two replays one update once; failing commands are given up after 3 attempts |

Known follow-ups, not blocking: move-button wording (16:00 vs 03:00), canary zone `Pacific/Kiritimati` in the zone list, missing-table notice (C-9), first-install NetworkPolicy ordering is now fixed but untested on a cluster, the CREATEROLE requirement for the owner role, about 30 older pyright errors in test files, and pinning CI tool images by digest.

## Approvals

| What | Who | When |
| --- | --- | --- |
| Spec | Marco | 2026-11-09 (front matter of the spec) |
| Merging every pull request after green CI | Marco, standing instruction | during the build |
| ADR-0029 Sealed Secrets | Marco | 2026-11-10 |
| ADR-0030: SCRAM verifier set by the client, mutation check nightly and on manual start | Marco | 2026-11-10 |
| Production | Not asked yet | |

## Deploy

Not deployed. Before the first production sync (ADR-0012, ADR-0025, ADR-0029):

1. Install the Sealed Secrets controller and back up its private key outside the cluster.
2. Seal `mail-triage-migration` and `mail-triage-secrets` with the same runtime password (procedure in `deploy/charts/worker/README.md`).
3. The owner role needs `CREATEROLE`; `DATABASE_OWNER_URL` should carry `?ssl=verify-full` where the database offers TLS.
4. Argo CD runs the migrate Job (PreSync) before the worker starts; a failed Job stops the sync and the old worker keeps running.

Rollback: sync the previous chart revision. Migrations 0004 to 0007 have tested downgrades; the runtime role is left in place.

## Validation package

Not applicable: not a GxP system (ADR-0006).
