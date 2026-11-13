# app chart

Deploys the web app (`api` and `web`) for a local-only cluster (ADR-0037). Images are pinned by digest in the GitOps repository.

## What the chart enforces

- `api.replicas` is exactly 1 and the api has no autoscaler (ADR-0034): sign-in limits and the code store live in the process.
- NetworkPolicy: default deny; `api` and `web` accept ingress from ONE peer that selects the ingress-controller namespace and its pods (`networkPolicy.ingressController`); there is no `web-to-api` rule.
- `api` egress is the database (`networkPolicy.egress.database`), DNS (UDP and TCP 53) and the SMTP host and port (`networkPolicy.egress.smtp.cidr` and `api.config.smtp.port`). There is no TCP 443 rule and no wide address block. A NetworkPolicy matches addresses, so the SMTP host is given as a `/32` (or a `/24` to `/32` range) next to its name.
- Secrets are referenced by name; the chart renders no `Secret` and no ConfigMap with secret values.

## Plain settings (`api.config`, per environment)

| Value | Env var | Meaning |
| --- | --- | --- |
| `username` | `APP_USERNAME` | the one allowed user name |
| `emailAddress` | `APP_EMAIL_ADDRESS` | where the sign-in code goes (personal data, not a secret) |
| `smtp.host`, `smtp.port` | `APP_SMTP_HOST`, `APP_SMTP_PORT` | the SMTP server (STARTTLS) |
| `smtp.from` | `APP_SMTP_FROM` | the From e-mail address (`smtp_from`); the SMTP user is often not an address |
| `publicOrigin` | `APP_PUBLIC_ORIGIN` | `https://` origin of the edge |
| `noticeIntervalMinutes` | `APP_NOTICE_INTERVAL_MINUTES` | the agent run interval in whole minutes |

`APP_SMTP_FROM` is wired in the Deployment by this chart; the backend setting `smtp_from` is added in the unit that wires the api (U-38).

## Secrets (ADR-0029)

Create one SealedSecret named `<release>-api` in the release namespace with these keys:

| Key | Env var | Content |
| --- | --- | --- |
| `database-url` | `APP_DATABASE_URL` | URL of the web role, see below |
| `code-hash-key` | `APP_CODE_HASH_KEY` | at least 32 random bytes |
| `csrf-key` | `APP_CSRF_KEY` | at least 32 random bytes |
| `username-hash-key` | `APP_USERNAME_HASH_KEY` | at least 32 random bytes |
| `smtp-user` | `APP_SMTP_USER` | send-only SMTP account name (ADR-0036) |
| `smtp-password` | `APP_SMTP_PASSWORD` | its password |

The three keys must differ from each other. Seal every value from standard input so it never reaches a file, a shell history or a log. For each key (strict scope, bound to name and namespace):

```sh
# a random key: nothing to type
openssl rand -base64 48 | tr -d '\n' | kubeseal --raw --scope strict --name <release>-api --namespace <namespace> --from-file=/dev/stdin
# a typed value: read it silently, then pipe it
read -rs VALUE && printf %s "$VALUE" | kubeseal --raw --scope strict --name <release>-api --namespace <namespace> --from-file=/dev/stdin; unset VALUE
```

Put each output under `spec.encryptedData.<key>` of a `SealedSecret` named `<release>-api` and commit that file to the GitOps repository. Never commit a clear value or put one in a values file.

### Database URL

The web role connects with the asyncpg `ssl` setting `verify-full`, never libpq `sslmode`:

```text
postgresql+asyncpg://<web-role>:<password>@<db-host>:5432/<database>?ssl=verify-full
```

The database host name must be in the server certificate. The CA that signed it is trusted through the image trust store of the cluster, not through a chart value.

## Certificate expiry alert (optional)

`certAlert.enabled=true` renders a `PrometheusRule` that fires when the ingress certificate (`<release>-tls`) has less than `certAlert.daysAhead` days left (at least 14). It is off by default and needs the Prometheus operator and cert-manager metrics; it is a gate for production (D-7).

## Environment gates (U-web-settings-57)

- `environment` is `local`, `staging` or `production` and defaults to `production`. Production values are refused by the schema unless `certAlert.enabled` is true and `api.image.digest` and `web.image.digest` are set (`sha256:` plus 64 hex characters).
- `ingress.hstsAnnotation.key` must not be empty: the schema refuses `hsts: true` without a named mechanism. The controller stays an open point (D-7), so the key and the redirect and TLS minimum settings come from the environment values.
- The tests in `agents/mail-triage/tests/infra/test_ingress_gates.py` render every `deploy/envs/*/values.yaml` and name what is missing: an HSTS directive, an HTTP redirect or a TLS minimum of 1.2.
- Base images in both Dockerfiles are pinned with `@sha256`; Renovate keeps the pins current (`docker:pinDigests`).

## Checks

```sh
helm lint --strict deploy/charts/app -f deploy/envs/local/values.yaml
helm template app deploy/charts/app -f deploy/envs/local/values.yaml | kubeconform -strict -summary -
helm template app deploy/charts/app -f deploy/envs/local/values.yaml | kube-linter lint /dev/stdin
```
