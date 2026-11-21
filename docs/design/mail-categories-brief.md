---
feature: mail-categories
intent: INT-004
spec: docs/specs/mail-categories.md
design: docs/design/mail-categories-design.md
status: approved
approver: the user
date: 2026-11-14
---

# Mail categories: prototype brief

Route B of ADR-0009: the prototype is built here as `docs/design/mail-categories-prototype.html` (one self-contained page, fake data) and published as a private artifact for the user. Direction: Pebble (ADR-0035), light and dark.

## What the prototype has to answer

1. Is the Categories page quick to understand and edit on a phone: list, name, description, counts, "Other", "Older category"?
2. Does the page make clear what a save does: a rename only renames the label; a changed description or a delete creates a review; the warning appears before saving?
3. Is a review of 842 mails calm and safe: collapsed groups, per-group "Approve group" or "Keep all", per-mail checkboxes, selection counts, a button that says what it does, a summary before anything moves?
4. Are the building, waiting (delayed apply), result, skipped and failed states clear, and is it clear that nothing moves while a plan is built?

## Persona

The one mailbox owner, mostly on a phone, who looks at the page now and then, and the same person weeks later who has forgotten the details (UX review). Also a keyboard and screen-reader user.

## Screens and states

| Screen | Purpose and primary action | States |
| --- | --- | --- |
| Categories | See and edit the list; Save | loading, ready, not ready (agent still seeding), saving, saved, save failed, validation errors per field, conflict (409, list changed elsewhere), session expired, forbidden (lock), too many saves (429) |
| Save summary | Before saving, shows "Renames only change the label" and "Saving will create a review of up to N mails" and, when a pending plan exists, "This replaces the pending review and discards your decisions" | rename only, creates review, replaces review |
| Review moves, overview | See the plan and the groups; open a group | no plan, building ("340 of about 2 000 checked, nothing moves yet"), ready with groups, ready with cap reached ("1 200 not looked at"), scheduled ("moves at 14:20, Cancel"), applying, applied (counts, "Move back", empty labels named), replaced by a list change, cancelled, 403 lock, session expired |
| Review moves, group | Approve group, Keep all, select mails | collapsed, expanded, partial selection ("12 of 80 selected", "select all 80 in this group"), paging ("Load more"), skipped and failed with a plain reason ("You moved this mail yourself") |
| Approve summary | Dialog with counts per group, "labels only, nothing is deleted", "you can move back"; the button says "Move 842 mails to their new categories" | normal, above the threshold ("waits 15 minutes, you can cancel in Telegram") |

## Flow map

Categories -> (Save) -> Save summary -> Categories (saved) or Review moves (when it created a plan). Review moves overview -> group -> (select) -> Approve summary -> overview (scheduled or applied) -> Move back. The header navigation links Settings, Categories and Review moves (badge).

## Copy that must be literal

Page titles "Categories" and "Review moves"; field names "Name" and "Description"; helper text "The model reads the description. Say what belongs here, for example: Invoices, receipts and payment confirmations."; "Other" with "Mail that fits no category"; "Older category" with "Add to my list"; "Mail you put in the Gmail label Archive is never re-sorted."; "Renaming only changes the label name."; "Changes apply to new mail from now on. Older mail moves only after you approve a review." (R1); the approve button "Move N mails, labels only".

## Accessibility and responsive

Breakpoints 390, 820 and 1440 px; WCAG 2.2 AA; touch targets 44 px (whole row tappable); each sender and subject wraps and never truncates without a full-text option; group headers are disclosure buttons with `aria-expanded`; "n selected" announced in a live region; status never by colour alone; sticky action bar on mobile.

## Out of scope for the prototype

Real data, sign-in, Telegram (only described), the settings page, and the real API; plan sizes are simulated.
