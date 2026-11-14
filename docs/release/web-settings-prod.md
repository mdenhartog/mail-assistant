---
feature: web-settings
intent: INT-002
spec: docs/specs/web-settings.md
review: docs/reviews/web-settings.md
status: open
date: 2026-11-14
---

# Production release checklist: web settings

Two rows are closed by U-web-settings-74 (rows 2 and 7: the controller is decided and the production values file exists); everything else is open. The web settings feature is built and merged (R1 and R2) but not deployed: the production values, the Traefik objects of the chart and the Argo CD manifest are files only, and nothing applies them. Phase 9 (release) is never started without Marco's explicit approval; the last row of the table is that approval.

The items come from the security reviews of the three challenge rounds (`docs/reviews/web-settings.md`), the threat model (`docs/security/web-settings-threat-model.md`) and the decisions D-7, D-9, D-10, D-19, D-21 and D-22 of the plan (`docs/plans/web-settings.md`). The owner of every item is Marco unless another name is given; the evidence column says what has to be shown before the status may change to done.

## Checklist

| # | Item | Owner | Evidence needed | Status |
| --- | --- | --- | --- | --- |
| 1 | Two-step verification (or a passkey) on Marco's mailbox, the one that receives the sign-in code (R-1; ADR-0033, ADR-0036). | Marco | A dated note by Marco that the mailbox has it, with no screenshot of secrets. | Open |
| 2 | Ingress controller decision (D-21, SEC2-04, SEC3-02): which controller serves the local ingress, and that it does what the chart assumes. | Marco | ADR-0040 (Traefik, 2026-11-14). The chart renders the Traefik `Middleware`, `TLSOption` and redirect objects and the tests assert them (U-74). | Done (U-74); the proof on the real ingress is row 3 |
| 3 | Edge behaviour proven on the real Traefik ingress in staging (probe below). **Given** the staging ingress, **when** it is probed over HTTP and over HTTPS, **then** HTTP redirects to HTTPS, exactly one `Strict-Transport-Security` header with `max-age=31536000` (no `includeSubDomains`, no `preload`) is returned, TLS 1.1 is refused (TLS 1.2 is the minimum), and a 9 KB request body gets 413 (the cap is 8 KB). | Marco | The probe output (commands and responses with demo hostnames removed) attached to the review record; the same checks as a script in the repository if one is written. | Open |
| 4 | Certificate expiry alert delivery (D-7, W-9): an alert at least 14 days before expiry reaches Marco. `certAlert.enabled` is false by default and the production schema requires it to be true. | Marco | A test alert received (or a rule firing in staging) and the cluster's Prometheus operator and cert-manager metrics named. | Open |
| 5 | Private certificate authority and device trust (D-9): the CA is run by hand or by a cert-manager issuer, and Marco's phone, tablet and desktop trust it. | Marco | The issuer name in the environment values, and a browser on each device opening the staging page without a warning. | Open |
| 6 | SMTP relay and send-only account (D-10): provider, host, port, STARTTLS with a certificate the api verifies against the system trust store, account without mailbox access, credential as a SealedSecret. | Marco | The host and port in the environment values and in the NetworkPolicy (`networkPolicy.egress.smtp`, `api.config.smtp.port`); a real code mail received in staging; no CA setting in the chart. | Open |
| 7 | The production values files exist (`deploy/envs/production/values.yaml` and `mail-triage.yaml`) with every value Marco supplies marked `# REQUIRED`; the chart gates pass for them once supplied (`test_production_ready.py`). The gates are: an ingress host under `home.arpa` (the local suffix), TLS and HSTS on, `certAlert.enabled: true`, an image digest for the api, web and agent images, the trusted proxy CIDRs set (the api refuses to start in production with an empty list), and no override of the environment, the database settings, the trusted proxies or any limit. | Marco | The files exist and render only with the REQUIRED values (U-74). Still open for Marco: supply them in a reviewed pull request, after which `helm lint` and `helm template` of the supplied values pass (commands below). | Files done (U-74); supplying the values is open |
| 8 | Trusted proxy CIDRs of the real controller pods (`api.config.trustedProxyCidrs`, `trustedProxyHops`), and a staging test with two clients that land in separate rate-limit buckets. | Marco | The CIDRs in the values; a test that shows client A being limited (429) while client B is not. | Open |
| 9 | The retention purge runs only at deploy: it is the last step of the migrate job, an Argo CD PreSync hook, with no CronJob (D-19, AC-21). Either require a sync at least every 30 days, or accept that data may stay longer than 90 days (security events) and one year (audit) when no sync happens. | Marco | The decision, written here: "sync at least every 30 days" (with how it is ensured) or "retention bound accepted as: ...". | Open |
| 10 | Kit 0.5.0 architecture check (CR-01): PR #84 (`chore: upgrade to claude-sdlc-kit 0.5.0`) is merged. The architecture `model.json` is still a draft with empty responsibilities, so the check only warns. | Marco | The responsibilities of the model filled in and `node scripts/architecture.mjs check` free of warnings on `main`. | Merged (PR #84); the model is open |
| 11 | Accepted risks R-1 to R-5 have owners and a review date (below). | Marco | The table below stays current; the review on 2027-05-10 is in the calendar. | Open |
| 12 | A week of testing the local stack (D-22, started 2026-11-14): the whole feature with the real limits and TLS everywhere, in Docker on this computer, before any production step. The outcome is recorded by Marco. | Marco | A dated note by Marco in the review record: what worked, what did not, whether the week is passed. | Open (running) |
| 13 | Where the SealedSecret files live in the GitOps repository (ADR-0029): not decided. | Marco | The location decided and written in the production values or an ADR; the sealed-secrets controller named. | Open |
| 14 | The Traefik access log keeps the path and never the query string (an installation setting of Traefik, not of the chart). | Marco | The Traefik log setting, and a request with a query string in staging that shows no query string in the log. | Open |
| 15 | The Gmail OAuth client in production: a Google Cloud project whose consent screen has the publishing status "In production". In the status "Testing" Google expires refresh tokens after 7 days and the agent loses its mail access. | Marco | The status "In production" of the consent screen, noted with the date, and a refresh token that is older than 7 days and still works. | Open |
| 16 | Handling of `TOKEN_ENCRYPTION_KEY`: the key that encrypts the stored Gmail token. A lost or changed key means the stored token cannot be read and Marco gives consent again. | Marco | The place where the key is kept (as a SealedSecret value, never in Git) and a note that a lost key means a new consent. | Open |
| 17 | `api.config.publicOrigin` and `ingress.host` must name the same host (the origin is `https://` plus the host). Nothing checks this yet; a check is to be added later. | Marco | The two values compared in the reviewed values pull request; later a chart gate that fails when they differ. | Open |
| 18 | INT-005 changes how mail is sent: an own SMTP server (smtp4dev) replaces the relay of row 6 for the sign-in code. The specification follows after the week test and the change is an R2 variant. | Marco | The specification and the rows 6 and 17 revised for it, and a real code mail received in staging. | Open (not specified) |
| 19 | Marco approves production explicitly. Phase 9 is not started before this. | Marco | His written approval in the pull request or the review record, with the date. | Not given |

## Review the production values (nothing is applied)

Rendering reads files only. Without the REQUIRED values both commands must fail and name the missing value:

```sh
helm template app deploy/charts/app -f deploy/envs/production/values.yaml
helm template mail-triage deploy/charts/worker -f deploy/envs/production/mail-triage.yaml
```

To review the result, copy the two files to a scratch directory, replace every `REQUIRED` (table below) and run, with the real values and never with a secret:

```sh
helm lint --strict deploy/charts/app -f /path/to/values.supplied.yaml
helm template app deploy/charts/app -f /path/to/values.supplied.yaml > app.render.yaml
helm lint --strict deploy/charts/worker -f /path/to/mail-triage.supplied.yaml
helm template mail-triage deploy/charts/worker -f /path/to/mail-triage.supplied.yaml > worker.render.yaml
```

Check in `app.render.yaml`: one `Middleware` with `stsSeconds: 31536000` and nothing else about HSTS, a `redirectScheme` `Middleware` with scheme https on the Ingress at entry point `web`, a `TLSOption` with `minVersion: VersionTLS12`, a `buffering` `Middleware` with `maxRequestBodyBytes: 8192`, images by digest, `APP_ENVIRONMENT=production` and a non-empty `APP_TRUSTED_PROXY_CIDRS`. The tests do the same with fixtures: `cd agents/mail-triage && uv run pytest -q tests/infra/test_production_ready.py`. The release itself is phase 9: the real values go in through a GitOps pull request, with the same digests as on staging, after Marco's written approval. Marco applies the Argo CD file `deploy/argocd/application.yaml` by hand; no workflow does.

## Values Marco must supply (the `# REQUIRED` markers)

| Name | File and key | Who supplies it |
| --- | --- | --- |
| api-image-digest, web-image-digest | `envs/production/values.yaml`: `api.image.digest`, `web.image.digest` | The release image build (cosign signed); Marco approves the digest that passed staging. |
| agent-image-digest | `envs/production/mail-triage.yaml`: `image.digest` | The release image build. |
| web-username, web-email-address | `api.config.username`, `api.config.emailAddress` | Marco (personal data, not a secret). |
| public-origin, ingress-host | `api.config.publicOrigin`, `ingress.host` | Marco: a local name under `home.arpa` (ADR-0037); the origin is `https://` plus the host. |
| certificate-issuer | `ingress.clusterIssuer` | Marco: the cert-manager ClusterIssuer of the private CA (D-9). |
| smtp-host, smtp-port, smtp-from-address, smtp-cidr | `api.config.smtp.*`, `networkPolicy.egress.smtp.cidr` | Marco: the relay chosen in D-10; the CIDR is the relay as a /32. |
| database-cidr | `networkPolicy.egress.database.cidr` | Marco: the production database host as a /32. |
| traefik-pod-cidr | `api.config.trustedProxyCidrs` | Marco, from the real cluster: the pod network of the Traefik pods (row 8). |
| agent-secret-name, migration-secret-name | `mail-triage.yaml`: `envFromSecret`, `migration.secretName` | Marco: names of the Secrets that the SealedSecrets create (ADR-0029); no value is ever in Git. The api Secret is `<release>-api`. |
| database-ca-configmap | `mail-triage.yaml`: `database.tls.caConfigMap` | Marco: the ConfigMap with the database CA (`ca.crt`). |
| release-revision | `deploy/argocd/application.yaml`: `targetRevision` (both Applications) | Marco: the release tag the approved digests belong to. |

## Staging probe (row 3)

**Given** the staging ingress (Traefik with the chart installed, host `$HOST`, private CA file `$CA`), **when** it is probed over HTTP and over HTTPS, **then** HTTP redirects, exactly one HSTS header with `max-age=31536000` is returned, TLS 1.1 is refused and a 9 KB body gets 413:

```sh
curl -sI http://$HOST/                                   # 301 or 308 with Location: https://$HOST/
curl -sI --cacert $CA https://$HOST/ | grep -ci "^strict-transport-security: max-age=31536000"      # prints 1
curl -sI --cacert $CA https://$HOST/ | grep -i "^strict-transport-security" | grep -ci "includesubdomains\|preload"   # prints 0
openssl s_client -connect $HOST:443 -servername $HOST -tls1_1 -CAfile $CA </dev/null   # the handshake fails
openssl s_client -connect $HOST:443 -servername $HOST -tls1_2 -CAfile $CA </dev/null   # the handshake succeeds
head -c 9216 /dev/zero | curl -s -o /dev/null -w "%{http_code}\n" --cacert $CA -X POST -H "Content-Type: application/json" --data-binary @- https://$HOST/api/settings   # 413
```

Attach the output with the host names removed to the review record. On kind (Traefik from `deploy/kind/traefik-values.yaml`) the same probe applies with HTTP port 8081 and HTTPS port 8443.

## Not closed by U-74

- Traefik installed in the real cluster with its CRDs, its certificate handling and an access log that keeps the path and never the query string (rows 3, 8 and 14; ADR-0040).
- Certificate alert delivery (D-7, row 4), the private CA and device trust (D-9, row 5), the SMTP relay (D-10, row 6), two-step verification on the mailbox (R-1, row 1) and the 30-day deploy cadence for the retention purge (D-19, row 9).
- Where the SealedSecret files live in the GitOps repository (ADR-0029, row 13) and the sealed-secrets controller itself.

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
- The local week-test stack (U-73, U-75, U-76) is a test environment on this computer; it proves nothing about the production ingress, the production mail relay or the production Gmail client.

## Related

- [Review record](../reviews/web-settings.md)
- [Local stack operations](../operations/local-stack.md)
- [Specification](../specs/web-settings.md)
- [Plan, decisions D-7 to D-24](../plans/web-settings.md)
- [Threat model](../security/web-settings-threat-model.md)
