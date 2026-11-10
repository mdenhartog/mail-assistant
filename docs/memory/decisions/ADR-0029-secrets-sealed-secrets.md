---
id: ADR-0029
title: "Cluster secrets: Sealed Secrets, committed encrypted through GitOps"
status: accepted
area: security
tags: [kubernetes, argocd, secrets, sealed-secrets, mail-triage]
date: 2026-11-10
guardrails: [guardrail-kubernetes, guardrail-helm]
---

## Context

The `worker` chart (ADR-0025, unit U-quiet-hours-15a) references two Secrets by name and creates neither: the migration Secret (`DATABASE_OWNER_URL`, `RUNTIME_ROLE_PASSWORD`) and the worker Secret (all agent settings, with `DATABASE_URL` using the runtime role and the same password). Production runs on Kubernetes through Helm and Argo CD (ADR-0012), and no secret may be committed in clear text. Something has to bring these Secrets into the cluster.

## Decision

Sealed Secrets (Bitnami `sealed-secrets` controller). The operator encrypts each Secret with `kubeseal` against the cluster's public certificate and commits the resulting `SealedSecret` to the GitOps repository; the in-cluster controller decrypts it into the ordinary `Secret` that the chart already references by name. The chart itself does not change.

- Sealing scope is `strict` (bound to name and namespace), so a sealed value cannot be moved to another Secret or namespace.
- The runtime password is generated once and sealed into both Secrets; rotation means resealing both and syncing, after which the migration Job sets the new password on the role.
- The controller's private key is backed up outside the cluster, in the operator's password manager. Losing it means resealing every secret.
- Clear-text values never enter Git, a values file, a shell history or a log. `kubeseal` reads them from standard input.

## Consequences

- Everything stays in GitOps and Argo CD syncs the `SealedSecret`s with the rest; no extra service and no cloud secret manager is needed.
- The private key becomes a critical asset: its backup and a documented restore are part of the operator procedure.
- Sealed values are per cluster. A second cluster needs its own sealing; the local compose stack keeps using `.env`.
- No automatic rotation or central audit. Acceptable for one operator and two Secrets; revisit when more components share secrets.

## Alternatives

- External Secrets Operator with a cloud secret manager: best rotation and audit, but needs a secret manager that does not exist for this project yet; the natural step up when production moves to a cloud with one.
- SOPS with KSOPS or `helm-secrets`: also encrypted in Git, but more setup in Argo CD for no extra benefit here.
- Plain Secret applied by hand: outside GitOps, invisible to Argo CD and easy to forget; rejected.
