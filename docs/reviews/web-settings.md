---
intent: INT-002
spec: docs/specs/web-settings.md
plan: docs/plans/web-settings.md
pr: "https://github.com/mdenhartog/mail-assistant/pull/55 (prototype), #56 to #59 (plan and ADRs), #60 to #132 (units, fixes and decision records), #133 and #134 (documentation and plan), #135 to #144 (R2, the local stack and production preparation), the documentation PR docs/INT-002/web-settings-finish-r2"
release: not released
---

# Review record: web settings (login and settings page)

The feature was built through the pull requests #60 to #132 on `main` (one pull request per unit, plus the decision records #89, #107, #116, #122 and #129). The prototype came in with #55, the plan with #56 and the ADRs with #57 to #59. Units U-45 to U-47 (R2: reset to defaults, typed values kept across a session end) were built and merged on 2026-11-14 (#136, #138, #135), followed by U-73 to U-78 (the local week-test stack, production prepared for Traefik, the username hint and its normalisation; #137, #140, #141, #142, #143, #144). Nothing is deployed to production. The documentation of phase 8 is this record, the [user guide](../user-guide/web-settings.md) and the [production release checklist](../release/web-settings-prod.md).

## Gates

| Phase | Result | Evidence |
| --- | --- | --- |
| 1 Spec | Approved by Marco, 2026-11-09, revised 2026-11-10 and 2026-11-14 (AC-32, AC-33, R1/R2 corrected) | `docs/specs/web-settings.md` |
| 2 Threat model | Written, deltas of 2026-11-10 (twice) and 2026-11-13 (three rounds), data classification current | `docs/security/web-settings-threat-model.md` |
| 3 Design | Approved; ADR-0033 to ADR-0039 | `docs/design/web-settings-design.md`, `docs/memory/index.md`, prototype PR #55 |
| 4 Plan | 78 units (75 R1, 3 R2), decisions D-1 to D-24 | `docs/plans/web-settings.md` |
| 5 Build, test first | Every unit except the documentation unit U-72 merged, one pull request each (U-68 and U-69 share #132); R2 U-45 (#136), U-46 (#138) and U-47 (#135) merged 2026-11-14; U-73 (#137), U-74 (#141), U-75 (#140), U-76 (#143), U-77 (#144) and U-78 (#142) merged 2026-11-14 | `git log` trailers `Unit: U-web-settings-nn`, pull requests #60 to #144 |
| 6 Challenge | Three rounds, findings fixed or accepted below | this file, section Challenge |
| 7 Verify | Full verification run of 2026-11-13 on `main` 6a53669: every check exited 0, including `pip-audit` and `pnpm audit`. Mutation testing of the 12 pure modules: 0 % survivors (annotation mutants skipped, equivalent on CPython 3.14). | plan section "Changes made during the build" (workflow `mutation`, run 43319415821) |
| 7 CI | CI on `main` 103acc8 is green. The pull requests of 2026-11-14 passed their checks before merging (jobs that did not apply to the change were skipped): #135, #136, #138 (R2) and #140, #141, #142, #143, #144 had `docs`, `web` or `backend`, `security`, `images` where relevant, and `prod-like` all successful; #139 (docs only) had `changes` and `docs` successful. | `gh pr view <n> --json statusCheckRollup` of each pull request |
| 8 Finish | Documentation in the pull requests #133 and `docs/INT-002/web-settings-finish-r2`: spec, ADR amendments, design, plan, threat model, user guide, this record, the release checklist and the [local stack notes](../operations/local-stack.md). The R2 pages (reset, kept typed values) and the username hint have no new screenshots. | `node scripts/docs.mjs check` |
| 9 Release | Not started | [production release checklist](../release/web-settings-prod.md) |

The verification run of 2026-11-13 was done on 6a53669. The round 2 fixes after it (U-63 to U-67, U-49) and the round 3 fixes (U-68 to U-71) were merged afterwards, each with CI green; the full verification run was not repeated on 103acc8.

## Challenge

Three rounds of red team (RT), security review (SEC) and code review (CR, round 1 only), each against the then current `main`, with the moderator deciding where findings disagreed. No Critical finding in any round. Every finding got its own fix unit with the finding named in the unit title and in the plan.

### Round 1 (2026-11-13, `main` 67b137e): 10 RT, 12 SEC, 12 CR; two High (decoy lock-out, chart without trusted proxies)

| Finding | Fixed by | Pull request |
| --- | --- | --- |
| RT-01, RT-04, RT-06, SEC-02 (owner locked out by decoys, other clients or the cap) | U-53 | #115 |
| RT-02, SEC-01 (chart without trusted proxies) | U-52 | #108 |
| RT-03, RT-05, SEC-06 (limits after the session lookup, IPv6, unbounded counters) | U-51 | #113 |
| RT-07, SEC-03 (nothing stops repeated guessing) | U-55 (automatic lock, `/web_lock`) with U-48 (alert) | #121 |
| RT-08 (conflict marks hide where the other change came from) | U-61 | #111 |
| RT-09, SEC-04, SEC-08, SEC-09 (wrong codes not counted, mail while locked, mail text) | U-54 | #119 |
| RT-10, SEC-05, SEC-07 (HSTS, certificate alert, image digests) | U-57 | #110 |
| SEC-10 (database TLS for the agent and migrate job) | U-58 | #112 |
| SEC-11, SEC-12, CR-09, CR-11 (defaults and response headers) | U-59 | #117 |
| CR-03, CR-04, CR-10 (cookie builder, stale docs, retention constant) | U-60 | #120 |
| CR-02, CR-05, CR-12 (silent test skips, decoy check, journey waits) | U-62 | #118 |
| CR-07 (Undo burst identified by an explicit id) | U-56 | #109 |
| CR-01 (architecture check) | Kit 0.5.0 merged (PR #84); the model is still a draft, the check warns only | release checklist item 10 |
| CR-06 (user guide) | Done by the documentation pull request | this PR |
| CR-08 (hand-written boundary validation in `apps/web`) | Open, Low follow-up | |

### Round 2 (2026-11-13, `main` 6a53669): RT2-01 to RT2-09, SEC2-01 to SEC2-09

| Finding | Fixed by | Pull request |
| --- | --- | --- |
| SEC2-01, RT2-01 (garbage requests set the lock) | U-63 | #127 |
| RT2-03, RT2-04, RT2-05 (full decoy class visible, replacement by cookie only, limiter room for the owner) | U-64 | #124 |
| SEC2-02, SEC2-03, RT2-06, RT2-09 (contract version, count integrity, column grants, event index) | U-65 | #123 |
| SEC2-05, RT2-08 (environment override, digests everywhere) | U-66 | #125 |
| SEC2-07, SEC2-08 (digest domain separation, IPv6 event class) | U-67 | #128 |
| Retention (purge of security events and audit) into R1 | U-49 (D-19) | #126 |
| RT2-02 (one device with the username uses up the hourly budget) | Accepted as R-4 (Marco, 2026-11-13) | release checklist |
| SEC2-04 (ingress controller) | Open: gate before production, D-21 | release checklist items 2 and 3 |
| SEC2-06 (security events kept forever until the purge) | Closed by U-49 (purge, 90 days) and U-71 (also expired `web_notice_token`). Residual: the purge runs only at deploy time (PreSync), tracked as release condition 9 (SEC3-04) | #126, #131 |
| SEC2-09 (spec, plan and ADR text no longer matches the build) | Closed by this documentation pull request (U-web-settings-72) | this PR |
| RT2-07 (the web lock is observable) | Closed by U-69: a request is still stored while locked and only the mail is skipped; cooldown, caps and `attemptsLeft` look the same | #132 |

### Round 3 (2026-11-13, `main` be5db2f): RT3-01 to RT3-08, SEC3-01 to SEC3-08

| Finding | Fixed by | Pull request |
| --- | --- | --- |
| RT3-01, RT3-04, SEC3-01 (a guess against a decoy counted, an expired request counted every post) | U-68 | #132 |
| RT3-02, RT3-03 (swallowed decoys, the lock left a trace) | U-69 | #132 |
| RT3-05, SEC3-04 (the web role could forge security events, expired notice tokens stayed) | U-71 | #131 |
| RT3-06, RT3-08, SEC3-08 (case-insensitive env guards, pinned test image, disruption budget) | U-70 | #130 |
| SEC3-03, SEC3-05, SEC3-06 (contradictions between spec, ADRs, design and data classification) | This documentation pull request | |
| SEC2-04 and SEC3-02 (ingress controller gate) | Open, D-21 | release checklist items 2 and 3 |
| RT3-07 (no limiter total per /48) | Accepted as R-5 | release checklist |
| SEC3-07 (traceability: D-7 meant two things, SEC2-04, -06 and -09 named nowhere) | Closed by this documentation pull request: D-7 is the certificate expiry alert, the ingress controller is D-21, D-20 is the moderator decision of round 3; statuses recorded in the plan | this PR |

### What remains open

- The ingress controller decision and its proof in staging (D-21; SEC2-04, SEC3-02): HSTS, redirect, TLS minimum and the 8 KB body cap on the real ingress.
- CR-01: PR #84 (kit 0.5.0) is merged. The architecture `model.json` is still a draft with empty responsibilities, so `node scripts/architecture.mjs check` only warns.
- CR-08: hand-written boundary validation in `apps/web` (Low).
- RT3-07 (R-5) and the other accepted risks R-1 to R-5, reviewed on 2027-05-10.
- The "spent" rule of the wrong-code alert is kept in memory: after an agent restart the last 24 hours count again and the lock may be set once more.
- Residual of SEC2-06: the purge runs only at deploy time (PreSync); release condition 9 asks for a sync at least every 30 days or an accepted retention bound.
- Scope of `done`: R1 and R2 are built and merged. C-5 (keeping typed values), C-6 (Reset to defaults), AC-12 (second half) and AC-25 are described as built in the spec. Nothing is released.
- The documents disagreed in places, which the documentation pull requests corrected: the hourly cap counts every request including a failed send (D-16, AC-31); the alert, the lock and the purge are R1; AC-32 and AC-33 are new; R2 was marked "not built" until the R2 pull requests of 2026-11-14 were merged.
- The week test (D-22): Marco tests the local stack from 2026-11-14 for a week and records the outcome. The agent waits for the Gmail consent: Marco creates a new OAuth client in Google Cloud and runs the consent (see the [local stack notes](../operations/local-stack.md)).
- INT-005 (an own SMTP server, smtp4dev, for the sign-in mail): confirmed 2026-11-14; the specification follows after the week test and is an R2 variant.
- The conditions for production are in the [production release checklist](../release/web-settings-prod.md): rows 12 to 18 are new since the local stack work (week test, SealedSecret location, Traefik access log, Gmail client status, `TOKEN_ENCRYPTION_KEY`, origin against host, INT-005).

## Approvals

All by Marco unless stated otherwise.

| Date | Decision |
| --- | --- |
| 2026-11-09 | Spec approved. |
| 2026-11-10 | Sign-in by e-mailed code (ADR-0036) and local-only access (ADR-0037); the R1/R2 split (W5); the stronger web notice with Undo and lock (ADR-0033); one api replica (ADR-0034); Pebble design (ADR-0035); plan approved at the phase 4 gate (D-1 to D-12). |
| 2026-11-12 | Decoy login requests and `attemptsLeft` for unknown usernames (D-13, ADR-0038). |
| 2026-11-13 | Owner protection against lock-out and the wrong-code alert in R1 with an automatic lock after 15 wrong codes in 24 hours (D-14, D-15, ADR-0039); every code request counts towards the hourly cap, AC-30 wins over D-11 (D-16); R-4 accepted (D-18); retention purge into R1 (D-19). |
| 2026-11-13 | Moderator decisions of the challenge rounds: what the lock counts (D-17, round 2) and decoys never counted, no swallowed decoys, no trace of the lock (D-20, round 3, ADR-0039 amendments). |
| 2026-11-14 | R2 is built before production (U-45 to U-47); a week of testing in Docker before any production step (D-22); Traefik as the ingress controller (ADR-0040, D-21); the Gmail consent runs in the agent container for the local stack (D-23); the username is compared without surrounding spaces and letter case and the login page says it wants the username (D-24); INT-005 confirmed. |
| Not given | Approval of production. |

## Deploy

Not deployed, neither to staging nor to production, and the production values files (U-74) are files only: nothing applies them. The conditions, owners and evidence are in the [production release checklist](../release/web-settings-prod.md). No production approval has been given; phase 9 is not started until Marco gives it explicitly.

Rollback plan: nothing to roll back yet. The database side (the web role, the `web_auth` schema, the notice cursor) comes from migration 0008 and later ones in the agent chain, and the rollback of the application is the rollback of the Argo CD release. Locking web sign-in from Telegram (`/web_lock`) refuses every web sign-in without a redeploy.
