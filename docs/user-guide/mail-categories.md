# Choose your mail categories and review moves

Keep your own list of categories, each with a name and a description, and let the assistant file new mail under them. When you change a description or delete a category, you review which already filed mails would move, and nothing moves until you approve it.

## Before you start

- You need to be signed in to the web app (see [Change your settings on the web](web-settings.md)).
- The assistant files mail in Gmail with labels. It only changes labels: it never deletes or sends mail.
- The examples below use demo values.

The web app has three links at the top: **Settings**, **Categories** and **Review moves**. When a review has open items, a number appears next to **Review moves**.

## The Categories page

Open **Categories**. You see:

- One card per category with a **Name**, a **Description** and the number of mails in it ("12 mails").
- A card **Other** with the text "Mail that fits no category". The assistant files a mail there when nothing on your list fits. You cannot rename or delete **Other**.
- The line "When you save, new mail is filed using this list. Mail already filed stays where it is." and the note "Archive is left alone. Mail you put in the Gmail label Archive is never re-sorted."

The assistant files a mail only under a category of your list, or under **Other**. It never invents a category.

If the page says "Your categories are still being set up. This can take a few minutes.", the assistant has not yet written your first list. Tap **Check again** later.

### Write a good description

The description is what the assistant's model reads to decide where a mail belongs. Say what belongs in the category, for example: "Invoices, receipts and payment confirmations." Write it as plain text; it is shown as text everywhere.

### Add, change and delete categories

1. Tap **Add category** to get an empty card, or change the name or description on an existing card.
2. Tap **Delete** on a card to remove it. A notice "Removed Travel." appears in its place with **Undo**: "It is removed when you save. Mail already filed under it stays where it is."
3. Tap **Save changes**. A question lists what will happen, for example `Rename "Bills" to "Invoices"`, `Change the description of "Travel"`, `Remove "Newsletters"` or `Add "Receipts"`, with the buttons **Save changes** and **Keep editing**. When you rename a category, the question also says "Renaming only changes the label name."
4. After saving, the page says "Saved. Your list applies to new mail from now on." The assistant uses the new list the next time it runs.

While you have changes that are not saved, a line beside the button shows how many ("2 changes not saved"). On a small screen the save bar stays at the bottom of the screen. If you try to leave the page, the question "You have changes that are not saved. Leave without saving?" appears, with **Keep editing** and **Leave**. If your session ended or web sign-in is locked, you are taken to the sign-in page without this question.

### Rules for names and descriptions

When a value is not accepted, the field says why and nothing is saved:

- "Give the category a name." / "Say what belongs in this category."
- "Use at most 40 characters for the name." / "Use at most 500 characters for the description."
- "A name cannot contain a slash." and "A name cannot contain control or invisible characters."
- "That name is kept for the assistant. Pick another." (the names "Other" and "Archive" are reserved, also in look-alike spelling)
- "Another category already has this name." (letter case does not matter)
- "A Gmail label with this name already exists."

You can have at most 50 categories. At the limit the page says "You have reached the limit of 50 categories. Remove one to add another." An empty list (only **Other**) is allowed. A save without a change makes no new version and sends no notice.

### Renaming keeps your mail

A change of only the name keeps the category and its mail. The assistant renames the Gmail label; no review is made and the model is not asked. A change of a description or a deleted category leads to a review (see below).

### Older categories

If Gmail already has labels from the assistant that are not on your list, the page shows **Older category** (or **Older categories**) with the text "These Gmail labels exist but are not on your list. Add one to use it for new mail. Its mails stay where they are, and you can write a description for it." Tap **Add to my list** to take one over. Its mails are then part of the first review.

### When the list changed somewhere else

If someone or something saved a newer list than the one you loaded, saving is refused with "The list changed somewhere else. This is the newest list. Your changes were not saved; make them again." The page shows the newest list.

### Other messages

- "Too many saves. Wait a minute and try again." You can save at most 10 times an hour.
- "Some values were not accepted. Check the list and try again."
- "Could not save. Nothing was changed." with **Try again**.

## Telegram notices for the list

Every saved change is announced in the Telegram chat with the assistant, also in quiet hours. The notice says "Your category list was changed" with the number of changes and the time (in UTC). It shows each added, removed, renamed or re-described category first, with the text before and after, then the categories that did not change. It has two buttons:

- **Undo** restores the previous list as a new version. It says "Undo restores the list. Mail already filed stays where it is." If the list changed again since, nothing is undone and the bot says so.
- **Undo and lock web sign-in** does the same and locks web sign-in (see [Lock web sign-in](web-settings.md#lock-web-sign-in)).

Buttons only work in your own chat, once, and for a limited time. A second or late press changes nothing and says "Already done" or "Expired".

## The Review moves page

When you change a description or delete a category, the assistant checks your already filed mail again and prepares a review. It tells you in Telegram with numbers only, for example "Plan ready: 340 mails checked, 12 to move, 0 unclear, 0 not looked at. Review it in the web app." Mail in spam or trash, and mail in the Gmail label Archive, is never looked at.

Open **Review moves**.

- **No review.** "No review is open. A review appears here when you change a description or delete a category. Until then your mail is sorted into your categories as it arrives." Tap **Edit your categories** to go to the list.
- **Being prepared.** "340 of about 2 000 checked, nothing moves yet." with a progress bar. You can leave the page and come back. When the assistant could not look at older mail, a notice says "Older mail was not looked at" and how many; those mails stay where they are. Mail with two Assistant labels is left out, and the page says how many.

### Check and approve

When the review is ready, the page says "These mails would be filed differently with your categories. Nothing moves until you approve it, and only labels change."

1. Under **Mails that would move** each group is "from category to category" with the number of mails, an example ("For example: Demo Shop, "Your order has shipped"") and a status: "Not decided yet", "All 12 will move", "5 of 12 will move" or "Stays in place".
2. Tap **Look at these mails first** (or the group name) to open the group. Each mail shows the sender's name, the real address, the subject (all as plain text) and "Not decided yet", "Will move" or "Stays in place". Long groups load 100 mails at a time with **Load more**.
3. Decide per group with **Approve group** or **Keep all in place**, or tick mails and use **Approve selected (n)** and **Keep selected in place (n)**. **Select all 80 in this group** ticks the whole group, also the mails not loaded yet; **Clear selection** removes the ticks.
4. The bar at the bottom shows how many mails are not decided yet; they stay where they are. Tap the button that says what it does, for example **Move 12 mails to their new categories**. Under it: "Only labels change, nothing is deleted".
5. A question "Move 12 mails?" lists the number per group and says: "Each mail gets its new category label in Gmail. Nothing is deleted and nothing is sent. You can move them back afterwards. Mails you did not approve stay where they are." Confirm with the button, or tap **Not yet**.

A mail you do not approve stays where it is, and stays out of later reviews until you change the list again.

If the review changed while you were looking at it, the page says "The review changed. Nothing was changed. Reload it to see what is there now." with **Reload the review**.

### When the mails move

- A small approval moves right away: "Your mails are being moved. Only labels change. This page updates by itself."
- When you approve more than 50 mails within 24 hours (the default; the deployment sets the number and the waiting time), the assistant waits 15 minutes first. The page says "Your mails move at 14:20. Only labels change. To stop this, use Cancel in the Telegram message." Telegram sends "12 mails move in 15 minutes (at 14:20 UTC). Only labels change." with **Cancel the move** and **Stop it and lock web sign-in**. You can only cancel from Telegram, not on the page. After the waiting time, a late Cancel is refused and the bot says so.
- Before it moves a mail, the assistant checks that the mail is still where the review saw it. A mail you moved yourself meanwhile is skipped.

### After the move

The page says "12 mails were moved on 15 Nov at 14:20. Only labels changed; nothing was deleted." Telegram sends "Plan applied: 12 moved, 1 skipped." and names Gmail labels that are now empty so that you can delete them in Gmail yourself; the assistant never deletes labels. The message offers **Move back** and **Stop it and lock web sign-in**.

Mails that were not moved are listed under **Not moved**, with a reason such as "You moved this mail yourself, so I left it alone." or "Gmail did not accept the change. It stays where it was."

**Move back** (on the page, with the question "Move these mails back?", or in Telegram) gives every moved mail its old label again, except mails you changed yourself since. The page says "Your mails are being moved back" and later "Your mails were moved back". Asking twice changes nothing more.

### Other states

- "This review was replaced on 15 Nov at 14:20. You changed your categories, so a new review is being prepared. Nothing from this one was moved."
- "This review was cancelled on 15 Nov at 14:20. Nothing was moved."
- "This review was too old. Nothing was moved. A new review is made when your categories change."

## Lock and sign-in

When web sign-in is locked, the Categories and Review moves pages do not show a banner. A save or a decision is refused, nothing is stored, and the page takes you to the sign-in page. To unlock, send `/web_unlock` in the Telegram chat (see [Lock web sign-in](web-settings.md#lock-web-sign-in)). When your session has ended you also land on the sign-in page, and you sign in with the code as usual.

## Not included yet

- You cannot edit categories in Telegram; the web app is the only place. Telegram only offers Undo, Cancel, Move back and the lock.
- You cannot cancel a waiting move on the web page.
- You cannot filter or sort a review by sender.
- Several mailboxes and other Google accounts.
- The assistant keeps a daily count of how many mails you re-filed by hand and how many sit under **Other**. It is written to the assistant's own log and database, and no page shows it yet.

## Related pages

- [Mail categories specification](../specs/mail-categories.md)
- [Change your settings on the web](web-settings.md)
- [Quiet hours and other settings in Telegram](quiet-hours.md)
