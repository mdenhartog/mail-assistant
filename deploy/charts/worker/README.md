# worker chart

A background worker without an inbound port, always exactly one copy (for example `agents/mail-triage`).

```sh
helm upgrade --install mail-triage deploy/charts/worker -f deploy/envs/local/mail-triage.yaml
```

## Database migration (ADR-0025)

With `migration.enabled: true` the chart renders a `Job` that runs `python -m app migrate` **before** every install and
upgrade: an Argo CD `PreSync` hook (`argocd.argoproj.io/hook`) and, for use without Argo CD, a Helm `pre-install,pre-upgrade`
hook. The Job connects as the database **owner** role, applies the Alembic migrations under an advisory lock, creates or
updates the login role `mail_triage_runtime` and applies its grants. The worker connects as that runtime role (it owns
nothing, cannot run DDL) and exits with code 5 if the schema is not at the head its image expects. A failed Job (exit 6)
stops the sync, so the old worker keeps running.

### Operator step: create two Secrets before the first sync

The chart only **references** Secrets by name; it never creates one and no value belongs in a values file.

| Secret (name from values) | Read by | Keys |
|---|---|---|
| `migration.secretName` (e.g. `mail-triage-migration`) | the migration Job only | `DATABASE_OWNER_URL` (SQLAlchemy asyncpg URL of the owner role, which needs `CREATEROLE`), `RUNTIME_ROLE_PASSWORD` |
| `envFromSecret` (e.g. `mail-triage-secrets`) | the worker only | all agent settings, with `DATABASE_URL` using the user `mail_triage_runtime` and the **same** password as `RUNTIME_ROLE_PASSWORD` |

```sh
kubectl create secret generic mail-triage-migration \
  --from-literal=DATABASE_OWNER_URL="$OWNER_URL" --from-literal=RUNTIME_ROLE_PASSWORD="$RUNTIME_PASSWORD"
```

(read the values from your password manager into the shell; never type them into a file in Git). To rotate the runtime
password: change both Secrets, then sync; the Job sets the new password on the role. How these Secrets are provisioned
(plain Secret by the operator, sealed secrets, External Secrets) is an open decision; any of them works with this chart.

The Job pod has its own NetworkPolicy (DNS and the database port only) and the same hardened pod settings as the worker.
