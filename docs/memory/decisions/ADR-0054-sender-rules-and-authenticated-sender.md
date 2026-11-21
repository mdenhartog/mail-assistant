---
id: ADR-0054
title: "Sender rules act only on a sender that Gmail authenticated; one verifier for rules and pinned mail"
status: accepted
area: security
tags: [label-structure, mail-triage, gmail, spoofing, dmarc]
date: 2026-11-21
guardrails: [guardrail-gmail, guardrail-llm, guardrail-python]
---

## Context

A category may list senders (D4); a matched sender files the mail without the model choosing the category. The `From` header is attacker-controlled (threat model LS-1, LS-2, LS-19). ADR-0045 §4 and ADR-0048 §4 already define when the agent trusts a sender for pinned mail: the topmost `Authentication-Results` header from `mx.google.com`, `dmarc=pass` and a `header.from` equal to the `From` domain. The agent also has a weaker regex parser in `core/auth_results.py`.

## Decision

1. One function `authenticated_from_domain(headers, from_header) -> str | None` in `agents/mail-triage/app/core/authentication.py` is the only verifier. Pinned mail (ADR-0045, ADR-0048) and sender rules both use it; the weaker parser is removed.
2. The sender counts as authenticated only when the **topmost** `Authentication-Results` header comes from `mx.google.com` and shows `dmarc=pass` with `header.from` equal to the `From` domain. Anything else is "not authenticated": a header the sender wrote, `dmarc=pass` in a comment or an `arc=` result, `X-Original-Authentication-Results`, a header inside an attached `message/rfc822` part, two `dmarc=` results, `dmarc=fail`, no header, a different `header.from`, a missing, several or unparsable `From` (D16: no DMARC means the model).
3. Matching is a lookup on the exact address and on the domain and its suffixes (a domain entry matches only that domain unless its entry says `subdomains: true`, then at a dot boundary), compared as lower-case A-labels, built once per list version. Entries are plain strings, never patterns. The longest match wins. The matcher is a pure function in `category-policy`.
4. Domain entries for public mailbox providers and multi-tenant sending platforms are refused (D15); a full address on them is allowed. The lists are constants of `category-policy`.
5. A listed sender that is not authenticated goes to the model; the filing record says "sender rule not applied: sender not authenticated" and the Categories page counts such skips per entry.
6. Pinned mail wins over a sender rule.

## Consequences

- A forged `From` cannot place a mail or raise an always-notify alert as if it came from the real sender.
- Accepted risk AR-1: a legitimate or abused sender that passes DMARC (and platforms that relay text of anyone) is filed by its rule. The alert for such a mail says "content not checked by the model" and shows the verified domain.
- Small senders that fail DMARC never match their rule; the per-entry skip count makes this visible.
- Records accepted risks AR-1 and AR-3 of the threat model `label-structure-threat-model.md`.

## Alternatives

- Accept SPF or DKIM alignment as well: needs the Public Suffix List and fails on shared sending infrastructure. Rejected (D16).
- Trust the `From` header and rely on the user's list: LS-1, high likelihood, high impact. Rejected.
- Verify in the api or the web app: only the agent reads mail headers. Rejected.
