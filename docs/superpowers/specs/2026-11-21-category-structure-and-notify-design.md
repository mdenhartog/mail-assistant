# Design: the user's label structure, sender rules and "always notify" (proposed INT-008)

Date: 2026-11-21 · Status: draft, for the user's approval · Source: brainstorm of 2026-11-21

## Intent and why

The user researched their own mailbox (with Claude Opus) and wrote a label structure of about 43 labels with classification instructions (`gmail-labelstructuur.md`, kept with the intent as input). The categories built in INT-004 cannot hold it: names may not nest, a mail gets exactly one label, descriptions are limited to 500 characters, and there is no place for rules that apply to the whole list. The user also wants to be told about every new mail in categories they choose, to set the archive label in the app instead of an environment variable, and to re-sort old mail only when they ask for it.

This is a new intent (proposed INT-008), not an extension of INT-004: INT-004 is confirmed and 42 of 42 units are built (four lack their `Unit:` trailer on `main`), and this changes its contracts (`rebuild-not-patch`).

## Goals

1. **Nested categories.** A category name may contain `/` (for example `Huis/Energie`); the Gmail label is `Assistant/Huis/Energie`. This reverses the "no `/`" rule of INT-004 C-3, which the user calls a mistake.
2. **Topic plus extra labels.** A category is either a *topic* (a mail gets exactly one, or "Other") or an *extra label* (added next to the topic when it applies, for example `Facturen`). At most one topic and one extra label per mail, as the user's document says ("maximaal twee labels").
3. **Longer descriptions** (proposal: up to 1 500 characters) so the user's sender lists, "Niet:" and "Let op:" notes fit.
4. **General instructions.** One text field for the whole list (the user's working method and priority rules), given to the model with the descriptions.
5. **Sender rules (approach B, variant 2).** A category may list senders (full addresses or domains). A mail whose sender matches is filed there **directly, without the model**. A mail with no sender, or an unknown one, goes to the model as today.
6. **Always notify.** Every category (topic or extra label) has a checkbox "always notify". A new mail filed in a checked category gives a Telegram alert, in addition to the existing urgency alerts. A mail never gives two alerts.
7. **Archive label in the app.** The archive label name (today the agent setting `ARCHIVE_LABEL`, ADR-0052, default `Assistant/Archive`) is set on the Categories page, with the same validation as today.
8. **Re-sort only on a button.** A change of the list applies to new mail only. Re-sorting existing mail happens only when the user presses "Sort everything again"; it covers what is in scope today (inbox and `Assistant/` labels, not spam, trash or the archive label).
9. **Upload from a file, always.** The Categories page can load a list from a file at any time, not once. The user's document (43 labels) is the first file. The upload fills the editor with a preview; nothing is saved until the user confirms, and the normal validation and versioning apply. The file is YAML with name, kind, description, senders, always-notify and the general instructions; an upload replaces the whole list after the preview, and the app can export the current list in the same format so it can be edited and uploaded again (U10).

## Non-goals

- No change to how urgency is judged for mail that goes to the model (D7 of `mail-triage`, C-16 of `mail-categories`).
- No sender conditions on subject or body ("Odido only when the subject says *thuis*"): those stay in the description for the model.
- No new Telegram actions; an "always notify" alert uses the existing alert and its three actions.
- No deletion of Gmail labels (D18 stays).

## Anti-goals (a failure even if it works)

- Duplicate alerts for one mail.
- A forged sender address that places a mail in a category or triggers an alert as if it came from the real sender.
- Old mail moving without the user pressing the button and approving.

## Decisions taken with the user

| # | Decision |
|---|---|
| U1 | New intent, not part of INT-004 (proposed by Claude; the user did not object). |
| U2 | Nested names are allowed; the INT-004 rule against `/` was wrong. |
| U3 | Approach B: sender rules in code next to the model. |
| U4 | Variant 2: a matched sender skips the model completely. Accepted consequence: such a mail gets no urgency judgement and no extra label from the model; the "always notify" checkbox is the way to be told about it. |
| U5 | "Always notify" is a checkbox on every category, independent of the urgency alerts; no double alert. |
| U6 | The archive label is set in the app, not in an environment variable. |
| U7 | Re-sorting existing mail happens only when the user presses a button; a list change otherwise affects new mail only. |
| U8 | The list can always be loaded from an uploaded file (not a one-time seed). |
| U10 | The upload format is YAML; an upload replaces the whole list after a preview; the app exports the current list in the same format. |
| U9 | After the switch to the new list, the user presses "Sort everything again" themselves; the agent builds no first plan on its own. |

## Approaches considered

- **A. Rebuild the category model; the model reads everything,** sender lists are text in the description. Simplest, one place to maintain, but relies on the model applying sender lists every time.
- **B. As A, plus sender rules matched in code** (chosen). Predictable, cheaper per mail, matches the user's step 1 ("sender first"). More to build and to maintain in the app.
- **C. Minimal: nesting and the checkbox, one label per mail.** Fastest, but an invoice from the dentist lands in either Tandarts or Facturen, which goes against the document.

Within B, variant 1 (sender fixes the topic, the model still judges urgency and extra labels) was offered and recommended by Claude; the user chose variant 2.

## How it behaves

### Filing a new mail

1. Security mail and the app's own sign-in code mail stay in the inbox (C-16, unchanged).
2. **Sender rule.** The sender is taken from `From` **only when Gmail's authentication result for that domain passes** (DMARC pass, or SPF/DKIM aligned with the `From` domain). An address rule matches the exact address; a domain rule matches that domain and its subdomains; the longest match wins. A match files the mail under the categories that list that sender, without a model call.
3. Otherwise the mail goes to the model with the general instructions and the list (closed set, as today). The model answers one topic id (or Other), at most one extra label id, urgency, reason, summary and confidence.
4. **Alert.** One alert when the mail is urgent **or** any of its categories is checked "always notify". The reason says which applies ("Category Facturen is set to always notify"). Quiet hours, the hourly cap (AC-26) and the daily overview work as today; a held alert is still one alert.

### Sorting again

The Categories page gets a button "Sort everything again". It starts a plan exactly as INT-004 R2 does (budget share, cap, Review moves, approval, Move back); sender rules apply in the plan too. The automatic plan after a list save (AC-33 debounce, AC-54 first-start plan) is removed.

## Constraints

- Category names: the INT-004 rules (length per segment, NFKC and case folding, reserved names "Other" and "Archive", no control characters) apply **per segment**; empty segments and leading or trailing `/` are refused; a Gmail label of at most 225 characters including `Assistant/`. A parent (`Huis`) is a grouping only: mail is filed under the full name. *Claude's call.*
- A sender may appear in at most one topic category and at most one extra label; a save that breaks this is refused with the reason. *Claude's call.*
- Sender rules are data from the user's own list, but the `From` header is attacker-controlled: matching only on an authenticated sender is a security requirement (threat model in phase 2).
- The general instructions and descriptions are untrusted text for the model, as C-4 says today; urgency rules stay fixed in the agent.
- The safety cap of 50 categories stays; 43 fit.
- Mail filed by a sender rule records "sender rule" instead of a model judgement in `filing`, so the AC-46 report and Move back keep working.

## Left to the builder

- Database shape of sender rules, the category kind and the checkbox (new list version contract, migration by the agent's chain).
- How the archive label setting moves from the environment to the shared list (ADR-0052 is superseded).
- Exact limits (description length, number of senders per category).
- The phases of `sdlc-flow` from here: intent INT-008, spec, threat model, ADRs (category contract v2, sender rules, archive label setting, manual re-sort), units.

## Open questions for the user

None. The first YAML file is converted from the user's document by Claude, as part of the build. The upload is parsed safely (`yaml.safe_load`, size limit, no anchors that expand, schema-validated) and is part of the threat model in phase 2.
