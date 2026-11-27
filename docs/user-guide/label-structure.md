# Build your own label structure: nested categories, sender lists and always-notify

Describe your whole mailbox structure on the Categories page or in one YAML file: nested categories such as `Huis/Water`, extra labels, senders that are filed without asking the AI, and a tick that sends you a Telegram message for every new mail in a category.

> Since INT-010 the assistant no longer uses the `Assistant/` prefix and the default archive label is `Archive`. See [Labels without the Assistant prefix](label-prefix-removal.md). Names below that start with `Assistant/` describe the earlier behaviour.

This page covers the whole feature: the category list, sender lists and always-notify, the YAML file, the name of your archive label and the button **Sort everything again** with its review of the mail that is not sure enough.

## Before you start

- You need to be signed in to the web app (see [Change your settings on the web](web-settings.md)).
- This page builds on [Choose your mail categories and review moves](mail-categories.md), which explains saving, undoing a removal and the older categories.
- The assistant files mail in Gmail with labels. It only changes labels: it never deletes or sends mail.
- All names, addresses and domains below are demo values.

## What changed for your existing mail

Changing the list never moves mail you already have. Only new mail follows it. The assistant no longer re-sorts the mailbox by itself after a change or at first start: old mail stays where it is, also after you upload 40 new categories. To move old mail, press **Sort everything again** (see [Sort everything again](#sort-everything-again)).

## Name your categories

Open **Categories**. The list shows one row per category with its name, the kind (**Topic** or **Extra label**), the number of senders ("No senders", "1 sender", "37 senders") and the checkbox **Always notify**. Tap a row to open it full screen; the **Add category** button opens an empty one.

- **Nested names.** Use a slash to nest a category under another one: `Huis/Water` sits under `Huis`. The Gmail label becomes `Assistant/Huis/Water`. A parent such as `Huis` is only a grouping: mail is filed under the full name, and `Huis` and `Huis/Water` can both exist. Parents have a button to collapse and expand their children.
- **Search and filter.** Use **Search categories** to find a category by name and the checkbox **Always notify only** to see only ticked ones. The page says how many categories match, or "No category matches."
- **Names.** Each part of a name has 1 to 40 characters. The whole Gmail label, `Assistant/` included, has at most 225 characters. Letter case does not matter for duplicates. The first part cannot be `Archive` or `Other`; those are kept for the assistant. A name cannot contain control or invisible characters, and an empty part (`Huis//Water`, a slash at the start or the end) is refused.
- **Number.** You can have at most 100 categories. At the limit the page says "You have reached the limit of 100 categories. Remove one to add another."

Mail that fits no category goes to the built-in **Other**. You cannot rename or delete it.

When a value is refused the field says why and nothing is saved, for example "Every part of a name needs text. Remove the extra slash or fill the empty part."

### Topic or extra label

Every category has a kind:

- **Topic.** Every mail gets exactly one topic. If nothing fits, it goes to **Other**.
- **Extra label.** Added on top of the topic, at most one per mail. Use it for a label that cuts across topics, such as `Facturen` (invoices).

So a mail has one topic and at most one extra label, never more.

### Description

The description is what the AI reads to decide where a mail belongs. Say what belongs in the category, in your own words, for example "Energy contracts, meter readings and yearly statements." It has 1 to 1500 characters and is shown as plain text everywhere. A condition on the subject line, such as "only when the subject says *thuis*", can only be written here; sender lists cannot hold conditions.

### General instructions

At the top of the list you find **General instructions**: text that applies to the whole list, for example how to treat mail in another language. It has at most 4000 characters. The AI reads it together with your descriptions; it cannot change the rules of the app, and it cannot make the assistant file mail outside your list.

## Add senders to a category

Mail from a sender that you list goes to that category without the AI choosing the category. In the full-screen view of a category, write one entry per line in **Senders**:

- A full address, such as `billing@energie.example.com`: matches only that sender.
- A domain, such as `energie.example.com`: matches mail from that domain only.
- A domain followed by `+subdomains`, such as `example.org +subdomains`: matches the domain and its subdomains (`mail.example.org`, `a.b.example.org`).

A live count shows how many entries you have ("37 of 100"; at most 100 per category). A line that is not accepted is marked with its line number and the reason. Some rules:

- Entries are plain text, never patterns or wildcards. Case does not matter.
- When two entries match a mail, the most specific one wins: an address beats a domain, and a longer domain beats a shorter one.
- An entry can be in at most one topic category and at most one extra-label category. If it is already elsewhere you read "`x.nl` is already in Huis/Energie. Remove it there first."
- You cannot list a whole domain of a public mail provider (such as `gmail.com`) or of a service that sends mail for many companies (such as `sendgrid.net`), because anyone can send from those. A full address on such a domain is allowed. The page says "A whole domain like this cannot be listed. Use full addresses instead."
- A category with no senders is judged by the AI as before.

A mail filed by a sender entry can have both a topic and an extra label when both categories list the sender.

### Why Gmail must confirm the sender

Anyone can write any "From" address on a mail. The assistant therefore trusts a sender entry only when Gmail itself has checked that the mail really comes from that domain (Gmail's own authentication result must say so). If Gmail cannot confirm the sender, or the mail has no usable From address or several of them, the entry is not applied and the AI judges the mail like any other mail.

Security mail and the sign-in code mail of this app are never filed by a sender entry; they are handled as before.

### Not applied N times

For each entry that Gmail could not confirm, the edit view shows how often it happened, for example "Not applied 3 times: Gmail could not confirm the sender", followed by "The AI judged those mails instead." The count holds only the entry and a number, never a sender address or subject. An entry you have just added or changed shows no count until it has been skipped again. The counts are dropped after 90 days without a new skip.

A high count usually means that the sender does not authenticate its mail or sends it through another domain. List the address instead, or remove the entry.

## Always notify

Tick **Always notify** on a category (the checkbox is labelled for screen readers with the full name, "Always notify, Huis/Water"), or in the edit view, and save the list as usual. You get one Telegram message for every new mail filed in that category, urgent or not. Alerts are limited per hour; the ones above the limit are sent together.

- **Never two alerts for one mail.** A mail that is urgent and in a ticked category, or in two ticked categories, gives one alert. It starts with its main label, "Urgent: needs your attention" or "Always notify: Huis/Water", and names every other cause on lines that start with "Also:".
- **An unticked category does not notify by itself**, but a mail the AI judges to need your attention still alerts, as before.
- **Quiet hours** apply: alerts are held and sent together at the end.
- **Only new mail alerts.** A mail moved by a re-sort or by the catch-up of old mail never gives an always-notify alert.
- **Three buttons**, as on every alert: Reply, Remind me later and No more reminders.

What an alert says about the sender:

- A mail filed by a sender entry shows "Verified sender domain" with the domain Gmail vouched for, and the sentence "Category not chosen by the model; urgency read by the model." It has no summary line and no clickable link, because the text was not checked: a legitimate sender or a service that relays text written by anyone can reach you under a trusted category name. Tick a category only when you accept that.
- A mail filed by the AI in a ticked category from a sender Gmail could not confirm carries the warning "Sender not verified: Gmail could not confirm who sent this. Be careful." and shows the real address, never only the display name.

## Replace the list from a YAML file

You can load your whole structure from a file at any time, and keep it as a file. Open **Categories** and find the section **Import and export** at the bottom.

1. Select **Download the template** to get a commented file (or **Download the example** for a small filled-in list). Change it to your own mail. See [What the fields mean](#what-the-fields-mean).
2. Select **Choose a YAML file** or drop the file on the box. The page says "Checking your file." Nothing changes yet.
3. Read the preview. It leads with the counts, for example 3 added, 5 changed and 2 removed, each with a word and an icon so that colour is not the only signal. Categories that the file does not contain are listed in their own block with the sentence "Removed categories disappear from the app. Their Gmail labels and mail stay as they are." If the general instructions change too, the preview says so, and if the file gives a different archive label it says "The archive label changes too."
4. Select **Replace my whole list** (with removals: "Replace my whole list (2 removed)", which is not selected by default), or **Cancel** to change nothing.
5. After a replace the page says "Your list was replaced." with the button **Restore previous version**.

Good to know:

- The upload replaces the whole list as one new version. Categories are matched by name (letter case ignored), so a category keeps its mail when the file has its name; a name that is not in the file removes the category, as a deletion on the page does.
- A preview is valid for 15 minutes and only for the browser session that uploaded it. If the list changed in between, you read "The list changed. Nothing was replaced. Upload the file again to see what it would change now."
- An upload that changes nothing makes no new version.
- One browser session can upload at most as many files per hour as the hourly limit for saving the list, which is 10 by default. Beyond that the page says "Too many changes to the list this hour."
- The file may be at most 256 KiB.

### Restore the previous version

**Restore previous version** makes a new version that is equal to the one before. The page says "The previous version is back." Restoring is itself a new version, so nothing is lost.

### Export your list

- **Download my list** saves `mail-categories.yaml`.
- **Copy my list** copies the same text. The page says "Copied." or "Could not copy your list."

The export has exactly the fields of the upload, so you can export, edit and upload it again; unchanged, it shows no change in the preview.

## What the fields mean

The file is plain UTF-8 text with the version line `schema: 1`. Indent with spaces, never tabs. The commented template that you can download explains every field; the short version:

| Field | Required | Meaning |
| --- | --- | --- |
| `schema` | yes | The version of the format. It must be `1`. |
| `generalInstructions` | no | The general instructions for the whole list, up to 4000 characters. |
| `archiveLabel` | no | The name of your archive label, saved with your list (see [Name your archive label](#name-your-archive-label)). A file without this field keeps the name you have now. |
| `categories` | yes | The list, in the order you want it, at most 100. |
| `name` | yes | The category name; nest with `/`, for example `Huis/Water`. |
| `kind` | no | `topic` (default) or `extra`. |
| `description` | yes | What belongs in the category, 1 to 1500 characters. |
| `senders` | no | Entries, each a plain address or domain, or the long form `entry: example.org` with `subdomains: true`. At most 100 per category. |
| `notify` | no | `true` or `false` (default `false`): Always notify. |

A small example:

```yaml
schema: 1
generalInstructions: Prefer the most specific category.
categories:
  - name: Huis/Water
    description: Water bills, meter readings and the water company.
    senders:
      - water.example.com
      - entry: example.org
        subdomains: true
    notify: true
  - name: Facturen
    kind: extra
    description: Any invoice or payment request, whatever the topic.
```

Write `true` and `false` exactly: `yes`, `no` and `on` are refused rather than read as booleans. Do not write a category called `Other` or `Archive`. The file carries no ids and no counts.

## When a file is refused

A refused file stores nothing. The page says "Nothing was changed. Fix these and upload the file again." and lists every problem on its own line with its place in the file, for example `Line 12, categories[0].senders[3]: This is not a valid address or domain.` The message is a fixed text and never repeats what you wrote. Use the copy button to copy the list of problems.

A file is refused when, for example:

- it is larger than 256 KiB ("The file is too large. Nothing was changed. Choose a smaller file.") or is not YAML ("That is not a YAML file. Nothing was changed. Choose a .yaml file, such as the template.");
- it uses a feature that the format does not allow: tabs, a byte order mark, anchors (`&`), aliases (`*`), merge keys (`<<`), tags (`!`), a key written twice or a field that does not exist;
- a name, description, sender or the general instructions break the rules above, or the same sender entry is in two topic categories or two extra-label categories;
- a whole domain of a public mail provider or sending service is listed;
- `archiveLabel` breaks the rules for an archive label name: a Gmail system label (such as `INBOX`), the label of one of your categories, a name inside `Assistant/` other than `Assistant/Archive`, or a name that is not a valid label name.

If the page says "Could not check the file. Nothing was changed. Try again in a moment.", the check did not complete; upload the file again.

## Name your archive label

The archive label is the Gmail label where you keep mail that the assistant must leave alone. On the **Categories** page the field **Archive label** shows its name; it starts as `Assistant/Archive`. Under the field you read: "Mail in this label is never sorted or moved. Renaming it renames the Gmail label, nothing else."

1. Change the name in **Archive label**.
2. Save the list as usual. The name is saved together with the list as one new version, and you get the usual change notice in Telegram.

What happens in Gmail:

- **The first time**, the assistant uses a Gmail label with that name when one exists, and creates it otherwise.
- **A later change renames that label** (it is found again by its id), so the mail in it stays protected. The assistant never creates a second archive label and never moves mail into or out of it.
- **A rename waits** until no plan is waiting or running (see [Sort everything again](#sort-everything-again)). New mail is sorted meanwhile.
- **If you rename the label in Gmail yourself**, the assistant does not follow it: it looks for the label by the name in your list, so it creates a new, empty label with that name. Change the name on the Categories page instead.

A name is valid when:

- it has 1 to 225 characters, no control characters, no space at the start or the end, no `..` and no empty part between slashes;
- it is outside `Assistant/`, or exactly `Assistant/Archive`;
- it is not a Gmail system label such as `INBOX`, `SPAM`, `TRASH` or `CATEGORY_...` (any letter case);
- it is not the label of one of your categories and lies below none of them.

A refused name stores nothing and the field says why, for example "This is a Gmail label of its own and cannot be your archive label." or "Use a name outside Assistant/, or exactly Assistant/Archive."

You can also set the name in the YAML file with `archiveLabel`. The upload preview says "The archive label changes too." when the file gives another name than you have; a file without the field keeps the name you have now.

## Sort everything again

Changing your list never moves old mail. When you want old mail filed by your current list, use the section **Sort everything again** on the **Categories** page.

### Ask for it

1. Type a number from 50 to 100 in **Confidence threshold (%)**. It starts at 50 and after that shows the number of your latest request. Under the field you read: "Mail from a sender rule always moves. Everything else the model is at least 50 % sure of moves by itself after a short delay, and each can be undone with Move back." The number in the text follows what you type. The page also says: "The model's confidence is its own estimate, not a calibrated probability."
2. Select **Sort everything again**. Under the button you read: "Nothing moves until a short delay; you can cancel in Telegram."
3. The page says "Your request is in. The assistant is preparing the plan and Telegram tells you what will move."

A number outside 50 to 100, a decimal, a sign or text is refused before anything is sent: "Use a whole number from 50 to 100."

### What moves by itself and what waits

The assistant looks at the mail in your inbox and in your `Assistant/` labels. It leaves spam, trash, sent mail, mail that carries your archive label, pinned mail and mail you rejected before alone. It then makes two plans:

- **Moves on its own.** Mail from a sender rule always, and every other mail whose model confidence is at or above your threshold. The delay always applies, also for a small number of mails, so you can stop it. After the delay the mail moves, and each mail can be undone with **Move back**.
- **Waits in Review moves.** Everything else: the mail whose confidence is below your threshold. Nothing of it moves until you approve it, as described in [Choose your mail categories and review moves](mail-categories.md). Mail with a very low confidence (below 60 %) is kept in this review too, so that your threshold decides what is shown.

Only a mail whose topic or extra label would change is in a plan. Only labels change: nothing is deleted or sent.

### The Telegram notice

When the plan that moves on its own is ready, Telegram sends a notice with numbers and a time only, for example "12 mails move on their own in 15 minutes (at 14:20 UTC). 7 wait for your review in the web app. Only labels change. Cancel the move or press Move back before then to stop it. Lock web sign-in stops web sign-in and cancels plans that still wait, until you send /web_unlock." It has three buttons:

- **Cancel the move** stops the plan before the time. After the waiting time a late Cancel is refused and the bot says so.
- **Move back** also stops it before the time. After the move, the result message offers **Move back** to put the mail back.
- **Stop it and lock web sign-in** locks web sign-in (see [Lock web sign-in](web-settings.md#lock-web-sign-in)) and cancels every plan that still waits. Use it when you think someone else used your session.

The web app has no Cancel button: you can only cancel from Telegram.

If an upload or a rename removes a category that a waiting plan moves mail into, the plan is cancelled and Telegram says so; mail that already moved stays where it is. When you save your list while a plan is waiting or running, that plan finishes; a review that is still waiting is replaced.

### Review moves with tips

The mail that waits is on the page **Review moves**:

- Every mail shows where it is now and where it would go, with the full nested names and both parts of the pair, for example "From topic Huis, extra none", "To topic Huis/Water, extra Facturen" and "Model confidence 72 %".
- For each category that has mail below your threshold the page shows a **tip**: a plain-text suggestion. It is labelled "This is a suggestion, nothing was changed." and has the link "Open the edit view of" that category. A tip never changes anything by itself and is never made a link; you decide whether to follow it. It is removed with the review.
- A line says how many mails already moved on their own, for example "5 mails were already moved on their own, 12 are scheduled and 1 was skipped." Mail that failed in Gmail is not counted in that line.
- Approve and reject work as described in [Choose your mail categories and review moves](mail-categories.md).

### When the button is refused

- **A plan is open.** While a plan is being prepared, waiting or running, the button is disabled and the page says "A plan is open. Wait until it has been applied or cancelled." with a link to Review moves. When the assistant refuses the request you read "A plan is already open or being prepared. Wait until it has been applied or cancelled."
- **Too many requests.** One session may ask as often per hour as it may save the list (10 by default): "Too many requests. Wait a minute and try again."
- **Not sent.** "Could not send your request. Check your connection and try again." Nothing was stored.
- **Sent twice.** A second request while the first is not yet a plan is refused, so nothing is stored twice.
- **The threshold could not be loaded.** The page says "Could not load the threshold." with **Try again**.

### Good to know

- The confidence number is the model's own estimate. A low threshold moves more mail by itself; the delay with Cancel, Move back and Lock is your control.
- Mail that moves on its own counts toward the amount that triggers the waiting time, like an approval of yours (see [When the mails move](mail-categories.md#when-the-mails-move)).

## Related pages

- [Choose your mail categories and review moves](mail-categories.md)
- [Change your settings on the web](web-settings.md)
- [Quiet hours and other settings in Telegram](quiet-hours.md)
