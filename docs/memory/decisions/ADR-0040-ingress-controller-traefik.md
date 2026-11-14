---
id: ADR-0040
title: "Ingress controller: Traefik, with its own objects for HSTS, redirect, TLS minimum and the body limit"
status: accepted
area: hosting
tags: [kubernetes, ingress, traefik, tls, hsts, web, mail-triage]
date: 2026-11-14
guardrails: [guardrail-kubernetes, guardrail-helm, guardrail-tls-certificates]
---

## Context

The phase 6 reviews (SEC2-04, SEC3-02) found that HSTS, the HTTP to HTTPS redirect, the TLS minimum and the 8 KB body cap are written into the values files in the vocabulary of ingress-nginx annotations, while the only Kubernetes environment (kind) runs Traefik. Nothing applies them on a real ingress, and the tests only read the values text. ingress-nginx is no longer maintained, its snippet annotations are a known critical risk class, and it sends HSTS with `includeSubDomains` by default, which ADR-0037 forbids. Open decision D-21.

## Decision

Marco agreed on 2026-11-14 to the recommendation: **Traefik** is the ingress controller for the local cluster and for production.

- The chart renders Traefik's own objects, not annotation text: a `Middleware` for the headers (`Strict-Transport-Security: max-age=31536000`, no `includeSubDomains`, no preload) and for the body limit (`buffering.maxRequestBodyBytes: 8192`), a `Middleware` or entry point redirect from HTTP to HTTPS, and a `TLSOption` with `minVersion: VersionTLS12`.
- The ingress allow-list peers of the NetworkPolicy and the trusted proxy CIDRs of the api (U-52) name the Traefik pods.
- The chart tests assert the rendered objects, and the staging probe of `docs/release/web-settings-prod.md` proves the real behaviour before production.

## Consequences

- `ingress-nginx` vocabulary leaves the values files, the schema gates and the tests (U-57, U-66 are adapted by U-74).
- Production still needs the Traefik installation, its certificate resolver or cert-manager issuer and the private CA (D-9) from Marco; nothing is deployed by this ADR.
- Changing the controller later is a rebuild of the ingress objects, not a flag.

## Alternatives

- Gateway API: the direction of the ecosystem, but more moving parts for one service on one cluster; revisit when the cluster uses it already.
- ingress-nginx: not maintained, snippet annotations, HSTS defaults against ADR-0037. Not chosen.
- HAProxy ingress or a cloud load balancer: no benefit for a local-only deployment (ADR-0037).
