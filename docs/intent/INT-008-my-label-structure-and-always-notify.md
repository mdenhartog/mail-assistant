---
id: INT-008
title: My own label structure, sender rules and always-notify
originator: the user
status: draft
date: 2026-11-21
amended: 2026-11-21 (after the phase 2 round table; confirmed on first writing, to be confirmed again)
---

## What I want

(English version, to be approved by the user; their own words are kept under *Original wording*.)

I researched my mailbox (together with Claude, with the Opus model) and wrote a label structure with classification instructions. I want the application to follow it instead of the categories it has now.

- **My structure becomes the list.** Names may be nested (for example `Huis/Energie`). A mail gets one topic label and, where it applies, one extra label such as `Facturen`. Descriptions may be long enough to hold my sender lists and notes, and the list has general instructions that apply to all categories.
- **Sender rules.** A category may name senders. When a mail's sender is named and Gmail confirms the sender is real, the mail is filed there directly and the language model does not choose the category (it is only asked whether the mail needs my attention, and only when the category is not ticked "always notify"). A category's sender list may be empty.
- **Always notify.** In every category I can tick "always notify". When a new mail is filed in such a category, I get a Telegram notification. This comes on top of what the agent already does: it keeps notifying me about mail it judges important from the content. I must not get two notifications for one mail.
- **Upload.** I can always load my categories from a file (a YAML file; an upload replaces the whole list after a preview; the app can export the current list in the same format). This is not a one-time action. A commented template file shows the format, so that another person who installs the agent can use it too.
- **Archive label in the app.** The name of the archive label, now an environment variable, I set in the application.
- **Sort again only on a button, with a threshold.** A change of the list applies to new mail only; the automatic re-sort of INT-004 goes away. Mail already in my inbox is re-sorted only when I press a button "Sort everything again" and type a percentage (it starts at 50). Mail the agent is at least that sure about moves without my review, after a short delay in which I can cancel in Telegram and can move it back; the rest I review first, as in INT-004. For every category with mail below the percentage the agent gives me a tip on what I could change in the category so that the percentage is reached.

## Why (the problem, who has it, how often)

I (the owner of the mailbox) cannot express my label structure in the application today: names may not nest, a mail gets exactly one label, descriptions are short and there is no place for rules that apply to all categories. I also only hear about mail the agent judges urgent, so mail in categories I care about (for example invoices) can go by unnoticed, and the archive label can only be changed by changing the environment.

## How I will know it works

- I can upload my list from a file, see a preview, and the Categories page then shows my nested categories with their description, senders and "always notify" tick.
- A new mail from a named sender lands in that sender's category without a model call.
- A new mail in a category with "always notify" gives me one Telegram notification, also when it is not urgent, and only one when it is also urgent.
- Changing the list or uploading a file does not move any old mail; pressing "Sort everything again" with my percentage moves what is at or above it after a delay and shows me the rest in a review that I approve before those move.
- For a category with mail below my percentage I see a tip on what to change.
- After two weeks I can see how much mail was filed by a sender rule, how many model calls were made per day, how many always-notify alerts came per day, how much mail is under "Other" and how often I moved back mail that the agent moved on its own.
- I can change the archive label name on the Categories page and the agent uses it.

## What it must not do

- It must not delete mail and must not send mail on its own (as in INT-001).
- It must not give two notifications for one mail.
- It must not move old mail without my pressing the button, and must not move mail below my percentage without my approving it; nothing may move at once, and everything that moved on its own can be moved back.
- It must not recommend or accept a sender that only a platform that relays text of anyone can vouch for.
- It must not place a mail by a sender rule on the strength of a forged sender address.

## Open questions

- A sender rule skips the model for choosing the category; in a category that is not ticked a small call still judges urgency (decided by the user in the round table, D11).
- A skill that scans a person's mailbox and writes the YAML file is proposed as its own intent. (the user)
- The `From` address can be forged. A sender rule must only act on an authenticated sender. (threat-model)
- An uploaded file is untrusted input (size, YAML parsing, schema). (threat-model)
- This reverses parts of INT-004 (no `/` in names, exactly one label per mail, 500 characters per description, automatic re-sort after a list change, the archive label as an environment setting). A new spec; INT-004 itself stays as it is. (spec phase)
- Sender and subject of mail are used in notifications and previews, as today (ADR-0018); no new personal data is stored. (threat-model)

## Original wording

> Ik weet niet of dat dit een nieuwe intent moet worden. Of dat je die bij 4 wil plaatsen. Maar ik heb een lepelstructuur gemaakt. En de manier hoe de agent de klassificatie van de e-mail moet doen. Wat ik daarnaast graag zou willen hebben. Is nu wordt er zo nu en dan wordt er een notificatie naar Telegram gestuurd. Maar ik wil eigenlijk de categorieën kunnen aankiezen. Of kunnen kiezen als daar iets nieuws in zit. Dat ik daarvan dan een berichtje krijg. [...] De labels zijn echt een onderzoek van mijn mailbox. Ook door Claude, door jou zelf, maar met het Opus model. En ik wil op basis daarvan dat de applicatie wordt aangepast zoals het nu is.
>
> Wat ik ook wil, is dat degene wat nu de mail order is, dat staat nu in een environment variabele, maar dat wil ik gewoon via de applicatie kunnen instellen. En ik wil, als ik een wijziging maak, dat ik toch alles opnieuw wil kunnen laten indexeren, wat er dan op dat moment nog in mijn inbox zit. En het allerlaatste is de Telegram agent, die zorgt er nu voor dat ik notificatie krijg. Dat moet zeker zo blijven. Echter komt er alleen één ding bij, is dat als ik een categorie aangeef, altijd notificeren.
>
> Geneste namen mogen wel degelijk.
>
> Ik wil alleen alles opnieuw categoriseren of sorteren als ik op een button druk. Dus en anders is het alleen met de nieuwe mail.
>
> Wat ik wil is dat ik in een categorie een vinkje kan zetten. Die aangeeft dat als daar iets nieuws in komt, dan moet je het altijd melden. En dat is buiten hetgeen wat je nu al hebt gemaakt. Uiteraard moet dat niet voor een dubbele melding zorgen.
>
> Facturen is maar een voorbeeld. Dus het moet bij elke categorie kunnen dat vinkje zetten.
>
> Ik wil dat je B kiest. [sender rules in code]
>
> Ja, ik wil nummer 2. Als er echt een afzender staat, want afzenders zouden leeg kunnen zijn, hè, dan moet het gewoon direct daar geplaatst worden. En dan kan je het model verder overslaan.
>
> Ik wil de categorieën altijd in de basis via een bestand kunnen uploaden. Dus dat is niet een eenmalige actie, maar ik wil dat het mogelijk is om categorieën vanuit een bestand te kunnen uploaden. En op je tweede vraag, ik druk zelf gewoon op alles nieuw sorteren.
>
> een YAML-bestand past.
>
> Als ik alles op nieuw sorteer, wil ik niet alles opnieuw hoeven te reviewen. Dus ik wil dat jij een bepaald percentage bijhoudt die ik zelf kan instellen. En als dat percentage bijvoorbeeld boven de 80% is, dat jij denkt dat dat mailtje in die categorie hoort, dan hoef ik geen review te doen. Valt die daar beneden, dan wil ik graag wel dat ik een review kan doen om zeker te weten of dat het daar hoort of dat ik nog iets moet aanpassen. Het zou wel fijn zijn als het onder zo'n categorie valt dat jij me misschien een tip geeft wat ik zou kunnen aanpassen in de categorie, zodat die bijvoorbeeld de threshold die ik heb ingesteld, want die wil ik wel elke keer zelf instellen, het toch haal.
>
> de grens die ik wil instellen, moet ik zelf met de hand kunnen instellen in de web UI. [...] Dat je daar op 50% begint, ik vind het best.
>
> [round table answers] 1,2,3, 4,5,6,7 aanbeveling volgen en akkoord, 8 eerste optie wil niet dat het uitgesteld wordt, Engels is toch als steeds zo, 10 mee eens, 11 mee eens maar maak ook een template mocht deze agent ook door anderen geinstalleerd worden met een skill die hun emailbox kan scannen in Claude, 12 eens.
