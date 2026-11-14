---
feature: web-settings
intent: INT-002
spec: docs/specs/web-settings.md
review: docs/reviews/web-settings.md
status: open
date: 2026-11-14
---

# Production release checklist: web settings

Nothing in this list is done yet. The web settings feature is built and merged (R1) but not deployed, and no production values file exists. Phase 9 (release) is never started without Marco's explicit approval; the last row of the table is that approval.

The items come from the security reviews of the three challenge rounds (`docs/reviews/web-settings.md`), the threat model (`docs/security/web-settings-threat-model.md`) and the decisions D-7, D-9, D-10, D-19 and D-21 of the plan (`docs/plans/web-settings.md`). The owner of every item is Marco unless another name is given; the evidence column says what has to be shown before the status may change to done.

## Checklist

| # | Item | Owner | Evidence needed | Status |
| --- | --- | --- | --- | --- |
| 1 | Two-step verification (or a passkey) on Marco's mailbox, the one that receives the sign-in code (R-1; ADR-0033, ADR-0036). | Marco | A dated note by Marco that the mailbox has it, with no screenshot of secrets. | Open |
| 2 | Ingress controller decision (D-21, SEC2-04, SEC3-02): which controller serves the local ingress, and that it does what the chart assumes. | Marco | Decision recorded as an ADR (`decision-gate`); the chart values for the environment name the HSTS mechanism (`ingress.hstsAnnotation`) and the controller settings (`ingress.controllerConfig`). | Open |
| 3 | Edge behaviour proven on the real ingress in staging. **Given** the staging ingress, **when** it is probed over HTTP and over HTTPS, **then** HTTP redirects to HTTPS, exactly one `Strict-Transport-Security` header with `max-age=31536000` (no `includeSubDomains`, no `preload`) is returned, TLS 1.1 is refused (TLS 1.2 is the minimum), and a 9 KB request body gets 413 (the cap is 8 KB). | Marco | The probe output (commands and responses with demo hostnames removed) attached to the review record; the same checks as a script in the repository if one is written. | Open |
| 4 | Certificate expiry alert delivery (D-7, W-9): an alert at least 14 days before expiry reaches Marco. `certAlert.enabled` is false by default and the production schema requires it to be true. | Marco | A test alert received (or a rule firing in staging) and the cluster's Prometheus operator and cert-manager metrics named. | Open |
| 5 | Private certificate authority and device trust (D-9): the CA is run by hand or by a cert-manager issuer, and Marco's phone, tablet and desktop trust it. | Marco | The issuer name in the environment values, and a browser on each device opening the staging page without a warning. | Open |
| 6 | SMTP relay and send-only account (D-10): provider, host, port, STARTTLS with a certificate the api verifies against the system trust store, account without mailbox access, credential as a SealedSecret. | Marco | The host and port in the environment values and in the NetworkPolicy (`networkPolicy.egress.smtp`, `api.config.smtp.port`); a real code mail received in staging; no CA setting in the chart. | Open |
| 7 | The production values file does not exist yet. When it is written, the chart gates must pass for it: an ingress host under `home.arpa` (the local suffix), TLS and HSTS on, `certAlert.enabled: true`, an image digest for the api, web and agent images, the trusted proxy CIDRs set (the api refuses to start in production with an empty list), and no override of the environment, the database settings, the trusted proxies or any limit. | Marco | `helm lint` and `helm template` of the production values pass; the values file is reviewed in a pull request. | Open |
| 8 | Trusted proxy CIDRs of the real controller pods (`api.config.trustedProxyCidrs`, `trustedProxyHops`), and a staging test with two clients that land in separate rate-limit buckets. | Marco | The CIDRs in the values; a test that shows client A being limited (429) while client B is not. | Open |
| 9 | The retention purge runs only at deploy: it is the last step of the migrate job, an Argo CD PreSync hook, with no CronJob (D-19, AC-21). Either require a sync at least every 30 days, or accept that data may stay longer than 90 days (security events) and one year (audit) when no sync happens. | Marco | The decision, written here: "sync at least every 30 days" (with how it is ensured) or "retention bound accepted as: ...". | Open |
| 10 | Kit 0.5.0 architecture check (CR-01): PR #84 (`chore: upgrade to claude-sdlc-kit 0.5.0`) is open; `node scripts/architecture.mjs check` must be green in CI on `main`. | Marco | PR #84 merged and the CI job green on `main`. | Open |
| 11 | Accepted risks R-1 to R-5 have owners and a review date (below). | Marco | The table below stays current; the review on 2027-05-10 is in the calendar. | Open |
| 12 | Marco approves production explicitly. Phase 9 is not started before this. | Marco | His written approval in the pull request or the review record, with the date. | Not given |

## Accepted risks

All five are accepted by Marco in the threat model and ADR-0039. Owner: Marco. Review date: 2027-05-10 for all of them.

| # | Risk | Where it is recorded |
| --- | --- | --- |
| R-1 | Whoever reads Marco's mailbox can sign in. Limited by the Telegram notice with Undo and the lock; item 1 is the condition for production. | Threat model, ADR-0033, ADR-0036 |
| R-2 | Anything on the local network can reach the login page. Bounded by the code limits and the request limits. | Threat model, ADR-0037 |
| R-3 | A guesser who knows the username can force the web lock with about 15 well-formed wrong codes in 24 hours; Marco unlocks with `/web_unlock` and Telegram stays available. | Threat model delta 2026-11-13, ADR-0039 |
| R-4 | A person who knows the username can use up the 5 codes an hour from one device and keep Marco from requesting a code for up to an hour (D-16, D-18). | Threat model delta 2026-11-13, ADR-0039 amendment |
| R-5 | The limiter keys an IPv6 client by /64 and has no total per /48, so a LAN device with many networks can send more than 30 requests a minute; the database limits still hold. | Threat model delta 2026-11-13 (round 3), ADR-0039 amendment 2 |

## Known limits that are not blockers

- The "spent" rule of the wrong-code alert is kept in memory in the agent. After an agent restart the events of the last 24 hours count again, so the lock may be set once more and the 10-minute notice may repeat. Marco lifts the lock with `/web_unlock`.
- The agent is not in the prod-like stack, so a full chain test of the web notice across the api and the agent belongs to staging.
- Reset to defaults (AC-25) and keeping typed values across a session end (second half of AC-12) are R2 and not built.

## Related

- [Review record](../reviews/web-settings.md)
- [Specification](../specs/web-settings.md)
- [Plan, decisions D-7 to D-21](../plans/web-settings.md)
- [Threat model](../security/web-settings-threat-model.md)
