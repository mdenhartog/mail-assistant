---
id: INT-004
title: Let me choose the mail categories myself
originator: Marco
status: draft
date: 2026-11-08
---

## What I want

(English version, to be approved by Marco; his own words are kept under *Original wording*.)

Before the agent creates a category label for a mail, the mail goes through a categorisation layer. In that layer I state which categories I want to have. The agent then follows them, so that my mail ends up in the right places.

As answered by Marco on 2026-11-08:

- I set the categories **only in the web application**, not through Telegram.
- A category has a **name and a description**. The description tells the language model why a mail belongs there, so it can choose the right category.
- A mail that fits none of my categories goes into the **"other" category**.
- When I change the list, the agent **sorts the mail it has already filed again**, so old mail follows the new list too.

## Why (the problem, who has it, how often)

Marco, for his personal mailbox. Today the agent invents the categories itself. On the first real run (2026-11-08) some mails were filed in places Marco does not want, and 36 of 75 old unread mails ended under "Other" because the agent had already reached its limit of 15 self-made categories. The list of categories is therefore not what Marco would choose.

## How I will know it works

- I can see my list of categories, with their descriptions, and change it in the web application.
- After I change the list, the next mails follow it: a mail is only filed under a category from my list, or under "other".
- Mail that was filed before is sorted again according to the changed list.
- The mails I looked at and did not like in the first run end up where I want them.

## What it must not do

- It must not delete mail (as in INT-001).
- It must not send any mail on its own (as in INT-001).

## Open questions

- Sorting existing mail again moves mail in my real mailbox in bulk. Which mails does it cover: only the mails the agent has filed itself, or also mail it has not touched? Should I see what will move before it happens? (Marco)
- When I change or delete a category, what happens to the mails filed under it: sorted again into the other categories, or into "other"? (Marco)
- The web application needs a login. Who may open it (only me), and does it use the Google sign-in of ADR-0008? That touches identity and the threat model. (decision-gate, threat-model)
- The web application and the agent must share the list of categories. Which of them owns it, and how does the agent get changes (it runs as a separate service with its own database)? (design)
- Descriptions are sent to the language model together with the mail. The same limits as today apply (ADR-0018), but the text of my descriptions becomes part of what the model reads. (threat-model)
- This reverses two decisions of the base spec: D1 (the agent chooses categories itself) and the non-goal "No rules editor", and it replaces the fixed maximum of 15 categories (C2). It also adds a screen, which the base spec excluded (non-goal "No web or mobile screen"). The change goes into a new spec. (spec phase)
- Is this one intent, or several (the category list and the web screen, the categorisation layer, sorting existing mail again)? (Marco)

## Original wording

> Ik wil dat je een intent maakt opnieuw. En dat er een soort categorisatie moet plaatsvinden voordat de mail een categorielabel aanmaakt. Dus ik wil dat een soort categorisatielaag komt waarin ik kan aangeven welke categorieën ik graag zou willen hebben. En dat moet ik ook aan de agent mee kunnen geven via een user interface. Zodat ik ook zodat de agent daarop gaat reageren en dat ik op die manier alles meer kan categoriseren in de juiste dingen. Want ik zie nu een aantal zaken al gecategoriseerd zijn op plekken die ik niet zo zou willen hebben.
>
> (Antwoorden op de vragen, 2026-11-08:) 1. alleen in te stellen via de web applicatie niet via telegram. 2. Naam plus ook een beschrijving waarom de LLM de juiste categorie kan bepalen. 3. Dan valt deze in de overige categorie. 4. ja
