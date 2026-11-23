---
feature: label-structure
intent: INT-008
spec: docs/specs/label-structure.md
extends: mail-categories-threat-model, mail-triage-threat-model, web-settings-threat-model
status: approved
revision: 2 (after the phase 2 round table, 2026-11-21)
approved: 2026-11-21 (the user)
date: 2026-11-21
approver: the user
asvs: "5.0"
---

# Threat model: label structure, sender rules and always-notify

This model adds to `mail-categories-threat-model.md` (list, plan, review pages), `mail-triage-threat-model.md` (Gmail, model, Telegram) and `web-settings-threat-model.md` (sign-in, session, CSRF, database roles). Threats that are unchanged there are not repeated; ids here are `LS-n`. ASVS references are to the chapters of ASVS 5.0 (item ids are set in phase 4). Criteria are `AC-n` of `docs/specs/label-structure.md` (revision 2).

## Scope

New in this feature: nested category names, topic and extra-label kinds, sender rules (a matched, authenticated sender is filed without the model choosing the category), the "always notify" tick and its alert, the urgency-only model call, the YAML upload, export and template, the general instructions, the archive label name in the list, the manual "Sort everything again" with a typed confidence threshold, system-approved plan items and tips per category.

Out of scope: sign-in and session design (unchanged), mail bodies in the web app (non-goal), several mailboxes (D7 of `mail-categories`).

## Data classification

| Data | Class | Note |
| --- | --- | --- |
| Sender entries (addresses and domains) | personal data (third parties' addresses) and internal | List data, shown on the Categories page and in the export. Never in a log, a URL or a Telegram text. |
| Matched sender entry in a filing record | personal data | Stays in the agent-owned filing record and its retention; the api gets no read access in this feature (C-17). |
| Uploaded YAML file | internal, untrusted input | Parsed in the api; not stored as a file, only the validated content becomes a list version. |
| General instructions, descriptions, tips | internal, sent to the model | Untrusted text for the model (C-3, C-15). Tips are untrusted model output. |
| Confidence value and threshold | internal | The threshold is stored on the request row; the confidence with the plan item. |
| Gmail `Authentication-Results` header | internal | Read by the agent only; kept as "authenticated yes or no" and the matched entry. |
| Archive label name | internal | Visible in Gmail. |
| Sender, subject in alerts and tips | personal data | As today (ADR-0018, ADR-0044); tips add one more model call that reads sender and subject, never the body. |
| Mail bodies, alert content, Gmail token | secret / personal data | Unchanged: unreachable for the api role (AC-20 of `mail-categories`). |

## Diagram

```text
Browser --[B1: local network, TLS, session + CSRF + Origin, unchanged]--> ingress --> web --> api
api --[B2: list v2 (select, insert); request_resort and user decisions only through database functions (ADR-0047)]--> PostgreSQL "categories"
agent --[B2': list read; plans, items; system approvals only through the agent's own function; filing records]--> PostgreSQL
Internet --[B5: sender-controlled mail, headers and text]--> Gmail --[B3: Gmail API, Authentication-Results added by Gmail]--> agent
agent --[B4a: mail text, descriptions, general instructions, tip input]--> Anthropic API (category call | urgency-only call | tip call)
agent --[B4b: alerts and plan notices]--> Telegram
User file --[B6: YAML upload]--> api (safe parse, schema, limits) --> preview (bound to session, hash, version) --> user confirms --> list version
```

Trust boundaries: B1 to B4 as in `mail-categories`; **B5** (mail from the internet to the decision "which category, which alert") and **B6** (the uploaded file) are new. B5 carries both the `From` header (attacker-controlled) and Gmail's authentication result (trusted only in its topmost, Gmail-added form).

## Threats

Likelihood and impact are L, M or H.

| id | element | STRIDE | threat | L | I | mitigation | criterion | ASVS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LS-1 | B5 sender rule | Spoofing | A forged `From` (or a display name that looks right) matches a sender entry: the mail is filed in a trusted category, the model does not choose the category, and an always-notify alert looks like it came from the real sender. | H | H | A rule acts only on a sender that Gmail itself authenticated: the single verifier of ADR-0045 and ADR-0048 (topmost header from `mx.google.com`, `dmarc=pass`, `header.from` equal to the `From` domain). Display name, `Reply-To`, subject and body never count. No DMARC pass means the model (D16). | AC-15, AC-19 | V2, V16 |
| LS-2 | B5 sender rule | Spoofing | Look-alike match: `evil-julianahoeve.nl`, `julianahoeve.nl.evil.com`, an IDN homograph, several `From` headers; a delegated subdomain of a trusted domain. | M | H | A domain entry matches the domain only; subdomains only with `subdomains: true` and then at a dot boundary; entries and the `From` domain are compared as lower-case A-labels; several, missing or unparsable `From` matches nothing. | AC-10, AC-13 | V2 |
| LS-3 | B5 sender rule | Spoofing | A domain entry for a public mailbox provider (`gmail.com`) or a multi-tenant platform (`amazonses.com`, `onmicrosoft.com`, `googlegroups.com`) would match every tenant or person on it. | M | M | Domain entries for public mailbox providers and multi-tenant sending platforms are refused (D15); a full address stays allowed. The lists are constants of `category-policy`. | AC-14 | V2 |
| LS-4 | Sender rule vs urgency | Tampering | A mail from a compromised or abused legitimate sender passes DMARC, so it is filed by the rule and never read for its category; text in it can steer the urgency-only call (suppress or raise an alert). | M | M | The urgency-only call has the fenced prompt and a closed schema (a boolean and a reason of at most 200 characters; any other answer means "needs attention"); alert text is escaped and length-capped with no masked links (AC-21 of `mail-triage`); the daily overview lists mail that was not alerted. Residual: AR-1. | AC-29, AC-21 | V1, V2 |
| LS-5 | B6 upload | Tampering / DoS | A malicious YAML file: alias bombs, merge keys, object tags, duplicate keys, huge or deeply nested input, YAML 1.1 words (`no`, `on`) read as booleans. | M | H | Size limit checked before parsing; the safe loader; every anchor, alias and merge key refused; duplicate keys and unknown fields refused; booleans never produced from words. | AC-32, AC-33 | V5, V2 |
| LS-6 | B6 upload | Information disclosure / Tampering | An error message, log line or audit record echoes file content back; a confirm replays another user's or an old preview; a cross-site form posts a file. | M | M | Errors name line and field, never the value; the preview is bound to the session, the file hash, an unexpired unused id and the list version (409 otherwise); upload and confirm need the session, the CSRF token and a matching `Origin` (403); canaries are searched for in all sinks. | AC-35, AC-36, AC-60 | V16, V14, V4 |
| LS-7 | B6 upload | Tampering | An upload replaces the whole list in one step: a mistaken or hostile file silently changes where new mail goes (and, with ticks removed, silences alerts). | L | H | Preview of what is added, changed and removed; one list version with an audit record; the change notice with an Undo token and lock (ADR-0033) applies to uploads; "Restore previous version" is offered. | AC-30, AC-31, AC-40 | V2, V16 |
| LS-8 | Names and archive label | Elevation | A category `Archive/Old` or an archive label inside a category path makes archived mail part of a re-sort; a name equal to a Gmail system label or a foreign label adopts or hides mail. | M | H | The first segment "Archive"/"Other" is refused; no category label equals or lies below the archive label; the archive name lies outside `Assistant/` or is exactly `Assistant/Archive` and is not a Gmail system label; a name equal to a foreign Gmail label is refused (AC-2 of `mail-categories`); label operations are limited to `Assistant/` plus the archive label by id. | AC-2, AC-42, AC-59 | V2, V8 |
| LS-9 | Archive setting | Tampering | Changing the archive label name renames labels in Gmail; a rename during a running plan changes which mail is in scope. | L | M | The rename waits until no plan is `scheduled` or `applying`; it renames by id and never moves mail into or out of the label; the change is announced (ADR-0033). | AC-41, AC-43 | V2 |
| LS-10 | System approval | Elevation | A model confidence inflated by mail text ("answer with confidence 100") gets a mail approved and moved without review. | M | M | The rule "confidence at or above the threshold" runs in code on the validated number; text cannot change the threshold, the target or the apply mode; the target is a category of the list; applying is delayed with Cancel, Move back and Lock; the minimum threshold is 50. Residual: AR-2. | AC-48, AC-49, AC-53 | V2 |
| LS-11 | System approval | Elevation / Tampering | The api approves items or sets a threshold that approves everything; the threshold is changed between the request and the build (time-of-check, time-of-use); a stolen session adds sender entries and presses the button so that sender-rule items move without review. | L | H | The threshold is fixed on an insert-only request row written by `request_resort`; the plan copies it; only the agent role approves, through its own function that re-checks confidence against the stored threshold (the api role gets SQLSTATE 42501); sender-rule items are applied after the delayed apply with Cancel, Move back and Lock, Undo or Lock cancels the plan, and system approvals count toward the rolling 24-hour wait (D17 accepted by the user). | AC-46, AC-49, AC-57 | V8, V4 |
| LS-12 | Tips | Tampering / Information disclosure | A tip built from many mails' sender and subject could contain markup, a link or an instruction, or recommend an attacker's sender ("add `evil.nl` to Facturen"); following it gives the attacker rule filing and a guaranteed alert. | M | M | Tips are plain text, length-capped and escaped; built only from the category, its description and sender and subject (never the body); a suggested sender is the authenticated domain of at least 3 below-threshold items, is shown with its count and is never on a refused list; never applied automatically; deleted with their plan items. | AC-52 | V1, V3 |
| LS-13 | Always notify | DoS | A noisy or hostile sender in a ticked category floods Telegram. | M | M | One alert per mail (also across a restart); quiet hours hold alerts; the hourly cap and batching apply; a mail moved by a re-sort or the backlog never alerts. | AC-24, AC-25, AC-26, AC-28 | V2 |
| LS-14 | Model calls | DoS | Urgency-only calls, tip calls and plan builds exhaust the daily model budget and starve new mail. | M | M | All count in the daily budget with the reserve of ADR-0021; when it is used up a sender-rule mail is still filed and listed in the overview; no call runs above the reserve. | AC-58 | V2 |
| LS-15 | Sender matching | DoS | 100 categories with 100 entries each, or a crafted entry, makes matching slow (patterns, quadratic loops). | L | M | Entries are plain strings; matching is a lookup on the exact address and on the domain suffixes of the `From` domain, built once per list version; limits on entries and categories apply. | AC-61, AC-10 | V2 |
| LS-16 | Audit | Repudiation | It is unclear why a mail was filed or alerted (model, sender rule and which entry, tick) or approved (threshold and confidence), or who changed a tick, the threshold, the archive name or uploaded a file. | M | M | The filing record names the source; plan items record the decision source, confidence and threshold; uploads, tick and archive changes have audit records with a keyed-digest actor and no mail text. | AC-18, AC-56 | V16 |
| LS-17 | Export | Information disclosure | The export leaks more than the list or is cached or rendered by the browser. | L | M | The export has exactly the upload fields; session-protected GET sent as an attachment with `nosniff` and `no-store`; the repository layer filters by mailbox id. | AC-37, AC-60 | V14, V4 |
| LS-18 | "Sort everything again" | Spoofing / DoS | A cross-site request or script starts plans repeatedly, burning budget and flooding Review moves. | L | M | Session, CSRF and `Origin` check, a database function, one non-terminal plan per mailbox and kind, an hourly limit, and a numbers-only Telegram notice. | AC-46, AC-36 | V4, V7 |
| LS-19 | Header parsing | Tampering | The `Authentication-Results` header is folded, duplicated, in a comment or an `arc=` result, in `X-Original-Authentication-Results` or in an attached `message/rfc822` part, so a parser reads "dmarc=pass" from the wrong place; Gmail adds no header at all and a forged one is read instead. | M | H | Strict parsing of the topmost header only, from `mx.google.com`; a missing, malformed, ambiguous or non-topmost result means "not authenticated"; table tests with forged, folded, duplicated and attached headers and with real anonymised Gmail headers. | AC-15 | V2 |
| LS-20 | Alert as a channel | Spoofing / Tampering | A platform that delivers text written by anyone passes DMARC under its own domain (PayPal invoice requests, Google Docs shares, DocuSign, LinkedIn messages): with a rule and a tick the text reaches Telegram unread, framed under a trusted category name. | H | M | Multi-tenant domains are refused as domain entries (a full address stays allowed); a sender-rule alert says "Category not chosen by the model; urgency read by the model" and shows the verified domain, with the reason inside a code span and no clickable or masked link (a reason that could become a link is refused); the user ticks a category knowingly. Residual: AR-1. | AC-14, AC-21 | V1, V2 |
| LS-21 | Always notify | Spoofing | Before this feature an alert needed an "urgent" verdict; now an unauthenticated mail only has to persuade the model that it is an invoice to raise an alert under a trusted category name. | M | M | An alert for a mail filed by the model without an authenticated sender says "sender not verified" and shows the real address, never only the display name; the same for a missing or unparsable `From`. | AC-22 | V1, V2 |

STRIDE coverage check: Spoofing (LS-1 to 3, 18, 20, 21), Tampering (LS-4 to 6, 7, 9, 11, 12, 19, 20), Repudiation (LS-16), Information disclosure (LS-6, 12, 17), Denial of service (LS-5, 13 to 15, 18), Elevation of privilege (LS-8, 10, 11). No STRIDE type is left unassessed.

## Accepted risks (accepted by the user on 2026-11-21; ADR in phase 3)

| id | risk | why it is acceptable |
| --- | --- | --- |
| AR-1 | A legitimate sender that is compromised or abused, or a platform that relays text written by anyone, passes DMARC and is filed by its sender rule without the model choosing the category, and with a tick its text reaches Telegram. Likelihood is high for platform senders. | The user chose sender rules (D4, D11). The harm is limited to a wrong label and an alert that says "Category not chosen by the model; urgency read by the model" with no clickable link; the urgency-only call, the escaped text, the refused platform domains and the daily overview bound it. |
| AR-2 | The model's confidence is its own report, not a calibrated probability; a mail can reach the threshold wrongly. | The user chose a threshold (D9). A delayed apply with Cancel, Move back for every item, the minimum threshold of 50 and the code-side rule bound the harm to a wrong label. |
| AR-3 | Gmail's authentication verdict is trusted. | Gmail is already the trusted source of the mail itself (ADR-0018, A-1); there is no better source on our side. |

## Open questions → decision-gate

1. AR-1, AR-2 and AR-3 are accepted by the user as written (2026-11-21).
2. ADRs to record in phase 3: sender rules and the authenticated sender; judging with topic, extra label and the urgency-only call; plan lifecycle as two plans, the confidence threshold and system approval; YAML upload as an input boundary; archive label name in the list (supersedes ADR-0052); always-notify alert; category contract v2. AR-1 to AR-3 are recorded as accepted risks.

## Outcome of the R1 challenge (phase 6, 2026-11-22)

The red-team, code-review and dependency-audit rounds ran on the R1 code. The dependency audit found nothing. The findings below were fixed in pull requests #194, #195 and #196, or are accepted or open as written.

| id | finding | threat | decision |
| --- | --- | --- | --- |
| RED-001 | Sender domains were compared with Unicode case folding, so a look-alike domain could match an entry | LS-19, AC-13 | Fixed (#195): domains are compared as A-labels (punycode), with no Unicode case folding |
| RED-002 | A model reason in the alert of a sender-rule mail could become a clickable link | LS-20, AC-21 | Fixed (#195): the reason is shown inside a code span and a reason that could become a link is refused; the alert wording is "Category not chosen by the model; urgency read by the model" |
| RED-003 | A mail with several `From` headers was read as having a sender | LS-19, AC-13 | Fixed (#195): several `From` headers mean no sender, so the mail goes to the model |
| RED-005 | The browser decoded the file again before sending it, which hid a byte order mark or an encoding problem from the checks of the api | LS-6, AC-32 | Fixed (#196): the web app sends the file bytes unchanged |
| RED-006 | One session could store thousands of previews within the purge window | LS-5 | Fixed (#194): a session may store as many previews per hour as the hourly limit for list saves (429 with `Retry-After`) |
| RED-007 | Parsing the YAML blocked the event loop of the api | LS-5 | Fixed (#194): the parse runs off the event loop |
| RED-004 | `archiveLabel` in an uploaded file is validated and stored with the list, but has no effect before R2 | LS-8 | Accepted for R1: the template, the example and the user guide say so. Decision pending for the owner: keep it stored, or refuse the field until R2 |
| RED-008 | A forged topmost `Authentication-Results` header for a mail that did not enter through Google's MX | LS-19, AR-3 | Accepted risk next to AR-3 (Gmail's verdict is trusted), unless a decision says otherwise |

Residual items and follow-ups:

- **Preview size.** `categories.upload_preview.content` has no database CHECK on its size. The api limits the file to 256 KiB, so the risk is low; a follow-up migration in `mail-triage` adds the constraint (the api cannot add DDL, ADR-0025).
- **Downgrade of 0024.** The downgrade of revision 0024 is lossy by nature: it drops the kinds, ticks, senders, general instructions and previews that did not exist before, so a rollback after users saved the new fields loses them.
- **Wording.** "Content not checked by the model" was replaced everywhere (see AR-1, LS-20, ADR-0054 and the plan of U-label-structure-10).
- **Alert text in ticked categories.** The sentence "urgency read by the model" is fixed text; for a sender-rule mail in a ticked category no model call is made (C-10), so the sentence says more than happens there. To be corrected in a follow-up (reported in the review record).

## Outcome of the R2 challenge (phase 6, 2026-11-23)

The red-team and code-review rounds ran on the R2 code (units 18 to 27 and 39). The fixes are on the feature branch (repair rounds A and B), so they land with the one pull request of the feature.

| id | finding | threat | decision |
| --- | --- | --- | --- |
| RED-R2-001 | The system approval could schedule a small plan to apply at once, so the notice with Cancel, Move back and Lock had nothing to stop | LS-10, LS-11, AC-46, AC-49 | Fixed: `approve_system_plan` always schedules the plan after the configured delay (at least a minute), whatever the 24-hour sum |
| RED-R2-002 | A tip could carry disguised markup, a link or a recommended sender that survived the cleaning | LS-12, AC-52 | Fixed: the tip is normalised (NFKC) and cleaned until nothing more changes; only code writes the suggested sender, from the authenticated domain of at least 3 items, never the model text |
| RED-R2-003 | An approval by the system was audited under the channel of the agent login (`telegram`) | LS-16, AC-56 | Fixed: the channel `system` is a constant in `approve_system_plan`; `plan_approval` and `apply_audit` accept it and the apply copies it |
| RED-R2-004 | The decide and approve functions could act on a plan of kind `auto` | LS-11 | Fixed: `record_decision` and `approve_plan` act only on a `review` plan |
| RED-R2-005 | Sent mail was in the scope of a re-sort | LS-8, AC-45 | Fixed: sent mail is out of scope, like spam, trash, the archive label, pinned and rejected mail |
| RED-R2-006 | The archive label name was checked by more than one rule | LS-8, AC-42 | Fixed: one rule in `category-policy` (`validate_archive_label`) serves the api, the upload and the agent |
| RED-R2-007 | The archive label is found by its name, not by a stored id; if the user renames it in Gmail, the agent creates a new, empty label | LS-9, AC-41 | Accepted limitation (the user is told to rename on the Categories page); follow-up: store the Gmail id |
| REV-001 | Three tests were stale after the R2 changes | n/a | Fixed |
| REV-002 | The move-back rate of system-approved items was not delivered | AC-63 | Delivered in the success numbers; it is a lower bound |
| REV-003 | Two copies of the archive name rule | LS-8 | Fixed: one rule (see RED-R2-006) |
| REV-004 | Missing tests for the findings above | n/a | Fixed: tests added |
| REV-005 | The modules `resort_apply`, `pg_resort` and `resort_build` are large | n/a | Follow-up: split them |

Known limits of R2:

- **No Cancel in the web app.** A waiting plan is cancelled only from Telegram (Cancel, Move back or Lock); the web app says so.
- **No agent in the prod-like e2e stack.** The R2 journey seeds the plans with SQL; the Gmail apply and the archive label rename are proven by the agent tests only, not end to end.
- **Failed items.** Items that failed in Gmail are not counted in the `auto` summary of the review plan.
- **Items below 60 % confidence** are kept in the review plan, so that the threshold of the user decides what is shown; they are not dropped by the agent.
- **Model calls per day** (tips included) is a lower bound, as in R1.
