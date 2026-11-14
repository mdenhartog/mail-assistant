---
intent: INT-002
feature: web-settings
---

# U-web-settings-38: Prod-like mail catcher with STARTTLS and the api service (R1)

- Layer: infra
- Contract: the mail catcher (existing `mail` service, port 8025) accepts SMTP with STARTTLS and a certificate from the internal CA in the prod-like profile; the `api` service gets its settings by reference (username, address, SMTP host `mail`, port, send-only credential of the catcher, keys, public origin of the edge, raised e2e limits) and trusts the internal CA through `SSL_CERT_FILE` (compose only; no CA or verify setting in the Helm values); a test helper `apps/web/e2e/support/mailbox.ts` reads the newest message and extracts the code from the catcher's HTTP interface.
- Files: `compose.yaml`, `deploy/prod-like/mail-tls.sh`, `apps/web/e2e/support/mailbox.ts`
- Depends on: U-web-settings-12, U-web-settings-37
- Parallel: no
- Guardrails: guardrail-compose, guardrail-docker, guardrail-tls-certificates
- Criteria:
  1. Given a code request through the edge, When the api sends, Then the catcher holds one message, received over STARTTLS with the CA-signed certificate (AC-29, W-14) (type: happy; level: image).
  2. Given the catcher is told to refuse STARTTLS, When a code is requested, Then no message arrives, the api logs the class only, and the response is still the success answer (AC-29, W-14) (type: security; level: image).
  3. Given the helper, When it reads the newest message, Then it returns the six-digit code and the subject has no code (AC-29) (type: happy; level: image).
  4. Given the api service environment, When rendered, Then every sensitive value is a reference, nothing is literal, and the raised limits exist only in the prod-like profile (AC-16) (type: security; level: ci).
  5. Given the default and `dev` profiles, When rendered, Then the raised e2e limits are not set there (type: security; level: ci).
  6. Given the api image start-up with a missing SMTP setting in the environment, When `up --wait` runs, Then the api does not become healthy and the log names the field (AC-4) (type: error; level: image).
