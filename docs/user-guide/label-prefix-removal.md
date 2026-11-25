# Labels without the Assistant prefix, the rename and the label cleanup

Your Gmail labels carry the names of your category list, such as `Aankopen/Marktplaats`, without `Assistant/` in front. This page explains what the assistant may touch, how to rename your existing labels once, and how the assistant removes empty labels after a waiting time that you set.

## Before you start

- You need to be signed in to the web app (see [Change your settings on the web](web-settings.md)).
- This page builds on [Build your own label structure](label-structure.md), which explains the category list and the YAML file.
- The assistant only changes labels. It never deletes or sends mail. The one thing it can delete is an empty label.
- All names below are demo values.

## What changed

- **No prefix.** The labels the assistant manages have the names of your list: `Aankopen/Marktplaats` instead of `Assistant/Aankopen/Marktplaats`. Nesting follows the slashes in the names.
- **Your list is the boundary.** The assistant only adds, removes, creates and renames the labels of the categories in your list, the label for **Other** and the archive label. Every other label is left alone, with one exception: it may delete it when it is empty (see [Label cleanup](#label-cleanup)).
- **Mail in scope.** A mail is looked at when it is in your inbox or carries one of those labels. A mail that only has a label outside your list, such as `Amerika`, is not touched.
- **The list comes from your file.** The first list is no longer made from the labels in Gmail. Until you upload your YAML file, the assistant does nothing with labels. See [Replace the list from a YAML file](label-structure.md#replace-the-list-from-a-yaml-file).

## Names for Other and the archive label

On the **Categories** page you find the fields **Other label** and **Archive label**. A new installation uses `Other` and `Archive`; you can change both.

- **Other label.** Mail that fits no category is filed under this label. Renaming it renames the Gmail label, nothing else.
- **Archive label.** Mail in this label is never sorted or moved (see [Name your archive label](label-structure.md#name-your-archive-label)).
- The names are saved with the list. A name that is not allowed is refused and the field says why.
- A category of your list cannot start with `Other` or `Archive`; those names are kept for these two labels. The old prefix `Assistant/` is refused as a start of a name as well.
- A name has at most 255 characters.

### A name that already exists in Gmail

When a name in your list is already a label in your Gmail, the assistant uses that label as it is: it keeps its name and its mail. It does not ask for a confirmation, and saving the same list again changes nothing.

## Rename your existing labels once

If you still have labels that start with `Assistant/`, the **Categories** page shows the section **Rename your labels**. Nothing is renamed until you confirm.

If the page says "Load your YAML file first: the list is no longer read from Gmail.", upload your list first with **Import and export** below.

### Read the preview

1. Open **Categories** and find **Rename your labels**. The page says how many labels and mails the plan covers.
2. Each label is a card with its name now (**Now**), its new name (**Becomes**) and its number of mails. Use **Sort by mail count** to show the most or the fewest mails first.
3. When the new name is a label you already have, the card says "Merge N mails into an existing label". The mail of the old label gets the existing label and loses the old one. Running it twice changes nothing.
4. The old labels of categories that are no longer in your list are in the preview as well. After the rename they are your own labels outside the list.
5. Choose **Skip** on a label to keep its name. The card says "Skipped: keeps its name." If you skip every label, the page says "Every label is skipped, so there is nothing to rename."

### Confirm by typing

1. Select **Rename these labels**. A dialog asks "Rename N labels?" and says how many labels you skipped. Mail stays where it is, and you can restore the old names afterwards.
2. Type the number of labels shown, or the word `RENAME`, in the field. This safety step stops a stray click from starting the rename. A wrong entry says "That does not match."
3. Select **Rename labels**, or **Cancel** to change nothing.
4. The page says "Renaming is in progress" and updates by itself. Telegram tells you when the rename is done.

If the plan changed since you opened the page, the page says "The plan changed. Nothing was renamed." and shows the new plan; check it and confirm again. If you skipped a label that is no longer in the plan, you read "A label you skipped is no longer in the plan." and nothing was renamed. If your session ended, your choices are kept: sign in again and come back.

### What the assistant does while it renames

- Until the rename is done, the assistant writes no labels at all: no renames, no new labels, no deletes. New mail that would go under **Other** stays where it is and is judged again at every check.
- Each label is read again just before it is renamed. A label that you renamed by hand after the preview is skipped and shown as kept.
- Mail stays on every label. Gmail apps may show the old names for a while.

### After the rename: restore

The page says "Renaming finished" with a summary such as "3 of 4 labels renamed, 1 skipped", and one line per label: renamed, merged, skipped or kept.

- **Restore the old names** asks the assistant to give every renamed label its old name again (by label, not by name). A dialog asks "Restore the old names?" with **Restore names** and **Keep the new names**. Telegram tells you when it is done.
- A restore does **not** undo a merge: mail that was moved onto an existing label stays there.
- The backup of the old names is kept for the retention period (see below) and is then deleted.
- When there is nothing to restore, the page says "Nothing to restore."

## Label cleanup

The assistant removes a label when all of these hold:

- it is a label you or the assistant made, not a Gmail system label such as `INBOX`;
- it is not in your list and is not the **Other** or archive label, and no label lies below it;
- it has no mail at all, also none in trash or spam, and no Gmail filter puts mail into it;
- it left your list at least the protection period ago;
- it stayed empty for the whole waiting time and is still empty at a final check just before the delete.

The assistant deletes at most one label per check, children before their parents. A mail arriving, or the label coming back into your list, starts the waiting again. It may also delete an empty label that you made by hand.

### The Label cleanup tile

On the **Settings** page the tile **Label cleanup** has three numbers. Each shows its range and default, and a value outside the range is refused with a message under the field.

| Setting | Meaning | Range | Default |
| --- | --- | --- | --- |
| Waiting time before a delete | How long a label stays empty before the assistant deletes it, typed as hours and minutes | 5 minutes to 12 hours | 12 hours |
| Protection period (days) | How long a label that left your list is kept, even when it is empty | 1 to 30 days | 7 days |
| Retention (days) | How long the list of deleted labels and the rename backup are kept | 7 to 90 days | 30 days |

The numbers are saved with the rest of the settings. A new waiting time applies only to labels that start waiting afterwards; a wait that is already running keeps its length.

### Recently deleted

The **Categories** page lists **Recently deleted labels**: the name of every label the assistant deleted and the day, for the retention period. The list is read-only. To get a label back, create it again in Gmail: the assistant cannot restore a deleted label or its mail, which is why a label is only deleted when it holds no mail.

### The daily Telegram message

You get at most one Telegram message a day about deleted labels, with a count only, for example "Label cleanup: 2 empty labels were deleted since the last note. The names are on the Categories page." No names are sent in Telegram, and none are written to logs.

## Good to know

- A restore does not undo a merge.
- Gmail has no delete that checks for mail first. A mail that arrives in a label in the very short time between the final check and the delete would lose that label; the mail itself stays in your mailbox.
- The old root label `Assistant` is deleted by the cleanup once it is empty, like every other label outside your list.
- Labels outside your list, such as `Amerika`, are never renamed or filled by the assistant.

## Related pages

- [Build your own label structure](label-structure.md)
- [Choose your mail categories and review moves](mail-categories.md)
- [Change your settings on the web](web-settings.md)
