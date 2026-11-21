---
feature: label-structure
intent: INT-008
phase: 2 (spec and threat model round table)
date: 2026-11-21
status: closed; the user answered the questions and approved the revised spec and threat model on 2026-11-21
---

# Round table, phase 2: label structure, sender rules and always-notify

Five independent reviews of `docs/specs/label-structure.md` and `docs/security/label-structure-threat-model.md`: product-owner, architect, security-architect, ux-critic, qa-strategist. The synthesis below was written by the main session (no separate moderator agent); every point comes from a report, and where reviewers disagree it says so. Nothing here is decided until the user answers the questions in the last section.

## Verdicts

| Reviewer | Verdict |
| --- | --- |
| product-owner | approve with changes |
| architect | approve with changes (three blockers that collide with built code) |
| security-architect | needs changes before approval |
| ux-critic | not ready as written (the screens are not designed) |
| qa-strategist | conditional pass |

## Consensus: changes to make without asking (a correction or a refinement of what the user decided)

| # | Change | From |
| --- | --- | --- |
| K1 | **Move AC-20 (no automatic plan) into R1.** The automatic plan of INT-004 (debounce after a list save, first-start plan) stays live in R1 and would start a whole-inbox plan on the first upload of 43 labels, against D8. R1 says plainly that old mail stays until the R2 button. Supersedes ADR-0046 §3 in R1. | product-owner, architect, qa |
| K2 | **One sender verifier.** Reuse the check of ADR-0045 and ADR-0048 (`core/pinned.py::_gmail_vouches`): the topmost `Authentication-Results` header must come from `mx.google.com`, with `dmarc=pass` and `header.from` equal to the `From` domain. Drop "or SPF/DKIM aligned" from C-5 (it needs the Public Suffix List and fails on shared infrastructure). AC-37 is rewritten: the topmost header must be Gmail's (if Gmail added none, a forged one never counts); `dmarc=pass` inside a comment, `arc=`, `X-Original-Authentication-Results` or an attached `message/rfc822` part does not count; two `dmarc=` results, `dmarc=fail`, or a `header.from` that differs means "not authenticated". | architect, security |
| K3 | **Threshold bound to the request, no web setting.** "Sort everything again" calls a `SECURITY DEFINER` function `request_resort(mailbox_id, confidence_threshold)` that writes an insert-only request row; the plan copies the threshold from it, so the value cannot change under a running plan (TOCTOU). The field "last used" is read from the latest request. The concept is called "confidence threshold" (ADR-0046 already has an approval-count limit). System approvals are written by an agent-only function that re-checks confidence against the stored threshold; the api role gets SQLSTATE 42501. System approvals count toward the D16 rolling 24-hour wait. Undo or Lock on a sort-again notice cancels the plan. AC-41 announces only the plan request (a threshold is no longer a setting to announce). | architect, security, product-owner |
| K4 | **Upload hardening.** Refuse every anchor, alias and merge key at parse time (this resolves the conflict between AC-16 and LS-5); keep YAML 1.1 words such as `no` and `on` as strings or refuse them, never booleans; duplicate keys refused; confirm is bound to the session, the file hash, an unexpired and unused preview id and the current list version (409 and nothing stored otherwise); CSRF token and `Origin` check on upload and confirm (403); the export is sent with `Content-Disposition: attachment`, `nosniff` and `no-store`; the file carries `schema: 1`. | security, architect |
| K5 | **Alert wording and trust signals.** A sender-rule alert shows the verified domain and "content not checked by the model" and no clickable or masked link. A mail filed by the model in a ticked category without an authenticated sender says "sender not verified" and shows the real address, never only the display name. The two kinds start with a fixed label: "Always notify: <category>" versus "Urgent: needs your attention". The spec names the hourly cap number instead of "as today". | security, ux |
| K6 | **Two labels on one mail.** `core/scope.py::classify` treats two `Assistant/` labels as UNCLEAR, so every mail with an extra label would fall out of re-sort, Move back and Undo. The filing record and the plan item carry a `topic_id` and an `extra_id`; classification is by kind from the list, not by label count. | architect |
| K7 | **Plan state machine.** A plan cannot be partly system-approved inside ADR-0046's plan-level approval. The build creates two plans: one system-approved (goes to `scheduled` with the D16 delay) and one review plan (`ready`); the one-non-terminal-plan rule becomes per kind. Rebuild, no flag. | architect |
| K8 | **Contract bookkeeping.** The migration adds columns with defaults to the existing rows (topic, no senders, not ticked); it does not insert a list version 2 (that would fire the insert-only trigger and the audit as if the user had edited). One confidence scale (0 to 1) in `category-policy`, and a stated relation to `LOW_CONFIDENCE = 0.6`. The archive label name lives on the list-level row with the general instructions. Superseded: ADR-0042 §5, ADR-0045 §1 and §3, ADR-0046 §1 to §4, ADR-0052. Extended: ADR-0047, ADR-0048, ADR-0021. Update `docs/architecture/model.json` in phase 3. | architect |
| K9 | **Edge cases and criteria quality** (qa). Add criteria for: topic and extra-label rules matching together; the same entry in two lists after an upload, including case-folded and punycode duplicates; threshold boundaries (49, 50, 50.5, "50 ", "abc", 100); a plan item whose target is removed by an upload or rename; an upload or list save while a plan is open; a mail with no, several or an unparsable `From`; `/` look-alikes (U+2215, U+FF0F) and label length 224/225/226; 100 categories with 100 entries; a mail arriving during an upload and an archive rename while mail is filed (two sessions, explicit barriers, the filing record names the list version); always-notify with quiet hours and the cap at N and N+1; one alert across a restart (idempotent insert keyed by mail id); double submit of confirm and of the button; down-migration. Split AC-1, AC-2, AC-10, AC-21, AC-23, AC-33. Renumber the criteria and constraints in order. Add 90 % coverage on changed code. A matrix `AC → test → layer` and the unit order are made in phase 4. | qa |
| K10 | **Screens** (ux). The spec gets a screens section: the Categories page is a collapsed list (indented name, kind chip, sender count, tick) with a full-screen edit view, search, a filter "always notify only", 44 px targets, collapsible parents; senders are one address per line in a textarea with a live count ("37 of 100"), errors per line and a plain conflict message; the upload preview leads with counts ("3 added, 5 changed, 2 removed"), shows removals in their own block ("their Gmail labels and mail stay as they are"), the confirm button reads "Replace my whole list (2 removed)" and is not the default focus when removals exist, errors give line and field (`line 12, senders[3]`) with a copy option, a "Restore previous version" action (LS-7 relies on it, no criterion today); a fixed explanation block ("Changing the list never moves mail you already have. Only new mail follows it."); help text beside Topic, Extra label, Senders (including why a listed sender may still go to the model), Always notify and the archive label; empty, unsaved-change and error states; nested list semantics, labels with the full category name, focus on errors, no colour-only states; export downloads `mail-categories.yaml` with a copy option and a commented example file; below the threshold field "Mail from a sender rule always moves. Everything else the model is at least <x> % sure of moves by itself, and each can be undone with Move back." and under the button "Nothing moves until a short delay; you can cancel in Telegram." | ux |
| K11 | **Skipped sender rules are visible.** A listed sender whose mail fails authentication is filed by the model; the filing record says "sender rule not applied: sender not authenticated" and the Categories page shows a per-entry count of such skips, so the user does not report a bug. | product-owner |
| K12 | **Fix the spec text:** the non-goals cite a "D13" that does not exist; the conversion of the user's document needs its own decision (see question 11). | product-owner |

## Where the reviewers disagree

| Topic | Positions | Moderator view |
| --- | --- | --- |
| Tips (C-15, AC-35) | product-owner: gold plating, nobody asked, later release. security: a tip built from many mails' sender and subject can recommend the attacker. ux: tips need a link to the category's edit view. | The user did ask for a tip ("a tip on what I could change"). The risk is real, so keep tips with constraints (below) rather than drop them. Question 8. |
| Default threshold | ux: 50 lets the model move mail it is half sure about unreviewed, suggests 80. | The user chose 50 as the starting value. Keep 50 and show the effect text of K10; mention the concern once. No question. |
| Sender-rule items and review | security: a stolen session can add sender entries, press the button and move mail with no review (confidence 100 bypasses any threshold). | Question 7. |
| Archive label | architect and product-owner: rename by id widens the Gmail allow-list, reverses ADR-0052's "adopt an existing label", and the user only asked to "set it in the app". | Question 4. |

## Questions for the user (each with the moderator's recommendation)

1. **Amend the intent.** INT-008 says the user approves before anything moves, and does not mention the threshold or tips. Amend "What I want", "How I will know" and "What it must not do" for D9 (sure items move without review, tips) and ask the user to confirm it again (allowed until the spec is approved). *Recommend yes.*
2. **R1 includes removing the automatic plan** (K1). *Recommend yes; the alternative breaks D8 on the first upload.*
3. **A re-sort and the extra label.** Does "Sort everything again" also change the extra label (for example add or remove `Facturen`), or only the topic? *Recommend: the plan target is a pair (topic, extra); an item exists when the pair would change.*
4. **Archive label.** Keep "renaming moves the Gmail label by id", or point the archive at an existing Gmail label ("adopt"), as ADR-0052 allowed? *Recommend: keep the rename (it keeps archived mail protected when the name changes) and also allow adopting an existing label when the archive label is set for the first time.*
5. **Platform senders and subdomains.** Mail from PayPal, Google Docs, DocuSign, LinkedIn, Google Groups, Microsoft tenants and mail-service domains passes DMARC with text written by anyone. *Recommend: refuse such multi-tenant domains as domain entries (a full address stays allowed), and match subdomains only when the user ticks "include subdomains" per entry.*
6. **No DMARC.** A sender without DMARC always goes to the model (DKIM or SPF alone does not count). *Recommend yes.*
7. **Sender-rule items in a re-sort.** They are approved without review whatever the threshold (confidence 100), because a verified sender is deterministic; the delayed apply with Cancel and Move back stays. Accept, or make them obey a review as well? *Recommend accept.*
8. **Tips.** Keep them in R2 with constraints: a suggested sender must be the authenticated domain of at least N below-threshold items and is shown with its item count, never a multi-tenant domain; a tip links to the category's edit view; tips are deleted with their plan items. Or defer them to a later release. *Recommend keep with constraints.*
9. **Language of the app and Telegram texts:** Dutch or English? (The user writes Dutch; the project writes English.)
10. **An upload that removes a category an open plan targets:** cancel the plan. *Recommend yes.*
11. **Your document becomes the first YAML file.** "Te beoordelen" becomes "Other" (not its own category); sender conditions on a subject (Odido "thuis") stay as description text; you review the converted file against your document before the first upload; the repository gets an anonymised copy as a golden test fixture, your real file stays out of it. *Recommend yes.*
12. **Success after two weeks** (product-owner): the share of new mail filed by a sender rule, model calls per day before and after, always-notify alerts per day, the share under "Other", and the Move-back rate of system-approved items. Agree on the measures now and set targets after the first two weeks.
13. **Accepted risks.** AR-1 is extended with the platform-sender case (likelihood high, not medium), AR-2 and AR-3 stay. Do you accept them as written once K5 and question 5 are in?
14. **Unparsable or missing `From`.** In a ticked category such a mail can only be filed by the model. Does it alert? *Recommend yes, with "sender not verified" (K5).*

## After the answers

The spec and the threat model are revised with K1 to K12 and the answers, INT-008 is amended and re-confirmed if question 1 is yes, and the user approves the revised spec and threat model (the phase 2 gate). Then phase 3 (design): the ADRs named in K8, the placement table, `model.json`, and the screen design of K10.
