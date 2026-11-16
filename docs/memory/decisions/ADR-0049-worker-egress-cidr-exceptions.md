---
id: ADR-0049
title: "Worker egress on 443 is limited by CIDR exceptions, not by host; an egress proxy or FQDN-capable policy is a later option"
status: accepted
area: security
tags: [mail-triage, kubernetes, networkpolicy, egress, helm]
date: 2026-11-16
guardrails: [guardrail-kubernetes, guardrail-helm]
---

## Context

Finding SEC-01 (Medium): the worker NetworkPolicy allowed port 443 to any address (a rule with ports and no `to`). That includes the cloud metadata service (169.254.169.254), the pod network and the service network. A Kubernetes NetworkPolicy cannot name hosts, so the three services the worker needs (Gmail, Anthropic, Telegram) cannot be pinned without a CNI with FQDN policies or an egress proxy.

## Decision

1. The HTTPS rule of the worker policy is one `ipBlock` with `cidr: 0.0.0.0/0` and `except` for `169.254.0.0/16`, the pod CIDR and the service CIDR. No egress rule is without `to`.
2. The pod and service CIDRs are chart values `networkPolicy.https.podCidr` and `networkPolicy.https.serviceCidr`. `values.schema.json` requires both, as an IPv4 CIDR with a prefix of 1 to 32 (so `0.0.0.0/0` and the empty string are refused). The chart default is the kind network; the production values mark both `REQUIRED`.
3. The migration Job policy stays DNS and the database port only (no 443).
4. Pinning HTTPS to the three services (an egress proxy, or a CNI with FQDN or L7 policies such as Cilium) is a later option and needs its own decision (`decision-gate`).

## Consequences

- Closes the path from a compromised worker to the metadata service and to cluster-internal services over 443.
- Accepted residual risk: a compromised agent can still reach any public host on 443, so data exfiltration over HTTPS is not blocked by the network layer. The other controls stay in place: secrets only in Secrets, no service account token, read-only root filesystem, no capabilities.
- Private ranges other than the cluster's own (RFC 1918 hosts outside the cluster, such as the database host) stay reachable on 443; the operator narrows this at the node or firewall level.
- Operators must set the right CIDRs per cluster; a wrong value only weakens the exception, it never blocks the pod.
- Not tested against a real CNI here: the tests check the rendered policy, not its enforcement.

## Alternatives

- Keep port 443 open to all: SEC-01 unchanged. Rejected.
- Egress proxy now: a new component and a new choice; larger than this finding. Deferred.
- FQDN-capable CNI (Cilium) now: changes the cluster choice. Deferred.
