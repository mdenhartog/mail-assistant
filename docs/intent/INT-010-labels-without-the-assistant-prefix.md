---
id: INT-010
title: Gmail labels without the Assistant prefix
originator: the user
status: draft
date: 2026-11-24
---

## What I want

(English version, to be approved by the user; their own words are kept under *Original wording*.)

All the labels in my Gmail mailbox that the assistant manages show the prefix `Assistant/` (for example `Assistant/Aankopen/Marktplaats`). I do not want that. I want the prefix gone, so the labels carry the names of my category list (`Aankopen/Marktplaats`).

The assistant may delete every label that holds no mail and is not in my list, except the standard Gmail labels. It always waits first: a label must stay empty for a time I set, up to 12 hours.

The label "Other" and the archive label have default names (`Other`, `Archive`) without the prefix; I can change them.

The labels that exist today under `Assistant/` are renamed by label id, so the mail on them stays where it is.

## Why (the problem, who has it, how often)

I have the problem in my own mailbox, every time I open Gmail: the prefix adds a level to every label and makes the list in the Gmail app long and hard to read (see the screenshot of the label drawer in the Gmail app, where every managed label starts with `Assistant/`). It is the first thing I see every day.

## How I will know it works

- In the Gmail app and on the web, none of the labels managed by the assistant starts with `Assistant/`; they show the names and nesting of my category list.
- The mail that sat on `Assistant/...` labels is still on the renamed labels; nothing is lost.
- A label that is empty and no longer in my list is removed by the assistant after the mail has moved out.

## What it must not do

- It must not rename or change the mail on any label that is not in my category list (for example `Amerika` or `Aiden Auto`), other than the archive label and "Other". An empty one may be deleted after the waiting time.
- It must not remove a label that still holds mail, that is still in my list or that is a standard Gmail label, and it must not remove one before the waiting time has passed.
- It must not lose or move mail when the labels are renamed.
- When a new name would clash with a label I made myself, it must stop and ask me, not choose.

## Open questions

- The prefix is today the safety boundary of the agent (it may only change labels under `Assistant/`) and the way it tells which mail is sorted. What takes its place? (Proposal in the conversation: the names in my current list plus the archive label, matched by label id.) Placement and the ADR follow in phases 1 to 3.
- The agent may not delete labels today (ADR-0046). Deleting empty labels widens that on purpose: it needs a decision and a threat model.
- The rename of existing labels needs a backup and a preview before it runs, and a rule for what happens on a name clash (see above).
- Which of my existing labels are in the list, and which are not? (Labels outside the list stay as they are.)
- Personal data: label names come from my own list; nothing goes outside my mailbox.

## Original wording

"Is dat voor al mijn labels staat in mijn Gmailbox staat assistant. En dat wil ik helemaal niet. Ik wil dat daarvoor weg."

"Alle labels mag de assistent verwijderen nadat alle mail daaruit verplaatst is en het label geen mail meer bevat en niet in de lijst staat."

"Hernoemen op id" (his choice for the labels that exist today).

"Hij mag alle labels weggooien behalve de standaard labels van Gmail. Wanneer deze leeg zijn. [...] hij daar altijd een tijd overheen moet gaan. En die tijd kan je zetten tot 12 uur." / "de naam other, dat is gewoon een default naam van de default archiefbak. Dus die moet je altijd gewoon als basis neerzetten en gebruiken. En iemand kan dat veranderen."
