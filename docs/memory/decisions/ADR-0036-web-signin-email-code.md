---
id: ADR-0036
title: "Web sign-in: username and a one-time code sent by e-mail"
status: accepted
area: identity
tags: [authentication, web, one-time-code, smtp, mail-triage]
date: 2026-11-10
supersedes: ADR-0024
guardrails: [guardrail-fastapi, guardrail-pydantic, guardrail-sqlalchemy-alembic]
---

## Context

ADR-0024 chose a generic OIDC provider (Google first) for the web page. Marco asked on 2026-11-10 for a different sign-in: a username, then a code sent by e-mail that is valid for a short time. His reasons: it is easier to test than an identity provider, and the whole management side is only available locally and not on the internet (ADR-0037). The page has one user.

## Decision

Sign-in by **username and a one-time code sent by e-mail**. There is no identity provider, no OIDC client, no discovery and no token validation.

- **Flow.** The login page asks for the username. The backend answers the same way whether or not the username is known ("If this username is known, a code has been sent"), with the same timing. For the one configured username it creates a login request and sends a code to the e-mail address that is configured on the server for that username; the address never comes from the request and is never shown in full (`m***@example.com`). The next page asks for the code.
- **Code.** Six digits from a cryptographically secure generator, valid for 10 minutes, usable once. Only a keyed hash (HMAC-SHA-256) is stored, together with the login request id, the expiry and the number of wrong attempts; comparison is in constant time. After 5 wrong attempts the code is dead. A new code replaces the previous one. A new code can be asked for after 60 seconds, and at most 5 codes are sent per hour for the username.
- **A failed send does not change the answer.** If the mail cannot be sent, the response stays the same as after a successful send, so it never shows that the username exists. The failure is logged and recorded as a security event, and the page tells Marco what to do when no code arrives ("No code after a few minutes? Ask for a new one after the countdown, or check the mail setup"). The 60 second cooldown counts every request, so a failed send also starts it; the hourly cap of 5 counts every request (changed on 2026-11-13, D-16: a refund for a failed send would make a known and an unknown username answer differently during a mail outage, so AC-30 wins; during an outage Marco waits at most an hour).
- **Bound to the browser.** The login request id is in a short-lived `__Host-login` cookie (`HttpOnly`, `Secure`, `SameSite=Lax`), so a code only works in the browser that asked for it.
- **After success.** The same server-side session as designed before: opaque id in `__Host-session`, 30 minutes idle and 12 hours absolute, derived CSRF token, change notices and the lock of ADR-0033. The session id changes at sign-in.
- **The e-mail.** Sent by the backend over SMTP with STARTTLS and a verified certificate, from a send-only account whose credentials are a SealedSecret (ADR-0029). The text contains the code and its validity, no link (no link prefetch, nothing to click) and no request details. The subject does not contain the code.
- **Limits.** The in-process limits of ADR-0034 apply to the code request and the code check, in addition to the per-code and per-hour limits above (the cooldown counts every request; the hour counts only sent codes). Refused and failed attempts are security events; the alert that counts them moves from "refused sign-ins by another account" to "wrong or expired codes" (still R2).
- **Testing.** In the local and prod-like stacks the existing mail catcher (port 8025) receives the message, so tests read the code from it. A time source and an id source are injected as before.

## Consequences

- Whoever reads Marco's mailbox can sign in. R-1 is restated this way; the Telegram notice with Undo and the lock (ADR-0033) still limit and reverse the damage. Two-step verification on the mailbox is a condition for production.
- The backend gets a send-only SMTP credential. It still has no access to Marco's mail (no reading, no Gmail scopes); the agent's Gmail consent is unchanged.
- Sign-in depends on mail delivery, which can take seconds to minutes; the page says that the code was sent and when it expires.
- No dependency on Authlib, joserfc, JWKS or a mock identity provider; the HTTPS-issuer start-up rule and the token checks disappear with them.
- Threats that replace the OIDC ones: guessing the code, mail flooding, interception of the e-mail, replay and username enumeration; they are in the threat model delta.

## Alternatives

- Generic OIDC provider (ADR-0024, superseded): strong and standard, but needs an external provider, a mock provider for tests and a public HTTPS origin.
- A link in the e-mail (magic link): no typing, but mail scanners and link previews can use the link before Marco does.
- Password with a second factor: more stored secrets and more surface for one user.
- The agent sends the e-mail through Gmail: no mail credential in the backend, but the code would arrive only after the next agent run, too slow for a code with a short life.

## Amendment 2026-11-14 (phase 8, consistency with D-16 and ADR-0039)

- **Every request counts towards the hourly cap.** The sentence under Limits, "the cooldown counts every request; the hour counts only sent codes", is superseded by D-16 (Marco, 2026-11-13; see the paragraph "A failed send does not change the answer"): the cooldown and the cap of 5 an hour count every code request from its creation time, also one whose send failed and for known and unknown usernames alike. Spec AC-29, AC-30 and AC-31 say the same.
- **The wrong-code alert is R1.** "Still R2" in the same bullet is superseded by ADR-0039: the alert after 5 wrong or expired codes in 10 minutes and the automatic web lock after 15 wrong codes in 24 hours are built and part of R1. What counts as a wrong code is in ADR-0039 amendments 1 and 2 (D-17, D-20).
