# Quiet hours and other settings in Telegram

Use `/settings` in the chat with your bot to see and change when the assistant may alert you: quiet hours, the daily
overview, the remind-me-later default and your time zone. When you travel, changing the time zone takes a few
messages.

## Before you start

- Only you can use this. The bot ignores every other Telegram account and chat.
- Nothing needs to be installed. The settings are kept in the assistant's database.
- The examples below use demo values.

## What `/settings` shows

Send `/settings`. The bot answers with four lines and, under them, a Change button for each line:

```text
Quiet hours: 23:00 to 07:00
Daily overview: 18:00
Remind-me-later default: 09:00
Time zone: Europe/Amsterdam
```

The buttons are Change quiet hours, Change daily overview, Change remind-me-later default and Change time zone.

Until you change something, the assistant uses exactly these values: quiet hours 23:00 to 07:00, daily overview at
18:00, remind-me-later default at 09:00 (what "tomorrow" means in a reminder) and the time zone Europe/Amsterdam. All
times are 24-hour clock times in the time zone you have chosen.

## What a change affects

- An alert that arises after a change is judged with the new values.
- An alert that was already held for quiet hours keeps the release time it got when it was held.
- A reminder you already snoozed keeps its due moment.
- A change takes effect within one run interval of the assistant (about a minute by default).

## Change a time

1. Send `/settings` and tap Change daily overview or Change remind-me-later default.
2. Type a time when the bot asks, for example `18:00`.
3. The bot saves it and shows the confirmation (see below).

You can type the time as `7`, `7:00`, `07:00`, `0700`, `19.30`, `7am` or `7:30pm`. `00:00` and `24:00` both mean
midnight. Seconds are not accepted. When the bot cannot read your answer, it says what it read, gives an example and
asks again.

## Change the quiet hours

1. Send `/settings` and tap Change quiet hours.
2. The bot asks "Quiet hours, step 1 of 2: start time". Type the start, for example `23:00`.
3. The bot asks "step 2 of 2: end time" and shows the start you gave. Type the end, for example `07:00`.
4. The bot saves both together and shows the confirmation. If you cancel, or the end is invalid, neither value is saved.

The rules, in plain words:

- Quiet hours last from 1 to 12 hours, counted on the clock.
- The start and the end must differ.
- They may cross midnight.
- The daily overview and the remind-me-later default must lie outside quiet hours. A time equal to the start is
  inside; a time equal to the end is outside.

When an answer breaks a rule, the bot names the rule, shows the value you gave and offers a working example, for
example "Quiet hours can be 1 to 12 hours. 22:00 to 11:00 is 13 hours." Nothing is saved and you can type a new answer.

### When the new quiet hours trap another time

If the new quiet hours would put the daily overview or the remind-me-later default inside them, the bot does not save
yet. It says which time is trapped and offers a button such as "Move to 07:00 and save". Tapping it moves that time to
the end of the quiet hours and saves everything together. Tap Cancel to keep the old values.

## Change the time zone

1. Send `/settings` and tap Change time zone.
2. Type a city or a country, for example `New York`, `Paris` or `Japan`. Upper and lower case and accents do not
   matter, and common short names such as `NYC` and `Wien` work.
3. If the bot finds exactly one zone, it saves it.
4. If there are several, the bot shows buttons (at most five) with labels such as "Paris, France (UTC+1)". Tap the one
   you mean. A country with several zones, for example `USA`, shows its zones with city names.
5. If you made a small typing error, the bot asks "Did you mean New York?" with a button to tap.
6. If it finds nothing, it says so and suggests the nearest big city or the country.

A zone name such as `Europe/Paris` also works when it is on the assistant's list of places. Text that cannot be a
place name (it must start with a letter and be at most 64 characters) is refused without a search. The list has a few
hundred large cities and all countries. A place that is not on it has to be added by a developer, so type the nearest
big city meanwhile.

The clock times do not move with the zone. After a change from Amsterdam to New York, quiet hours stay 23:00 to 07:00,
now on the clock in New York.

## The confirmation and Undo

After every change the bot sends "Saved." and the full picture. After a change of zone it looks like this:

```text
Saved.
Time zone: America/New_York (UTC-5)
It is now 17:05 there, 23:05 in Amsterdam.
Quiet hours: 23:00 to 07:00 New York time (05:00 to 13:00 Amsterdam time)
Daily overview: 18:00
Remind-me-later default: 09:00
Next overview: today 18:00
Next clock change: 2026-11-01 at 02:00 (UTC-4 to UTC-5)
```

The last line appears only when the clock changes within the next 14 days. The message has two buttons.

- **Undo** puts the previous values back. It works for 24 hours, and only if nobody changed the settings since.
  Otherwise the bot says the settings changed and changes nothing. After the very first saved change there is nothing
  to undo.
- **Show settings** shows the `/settings` card again.

## Cancel, expiry and conflicts

- **Cancel.** Every question has a Cancel button. The old value stays and the bot says "Cancelled. Nothing was
  changed."
- **A question expires after 15 minutes.** If you tap one of its buttons later, the message changes to "Expired"
  without buttons, and the bot offers Start again. Nothing was changed.
- **One question at a time.** If you send `/settings` while another question is open (for example a snooze or a reply
  to an alert), the old question is dropped and the bot tells you which one. Your next typed text answers the settings
  question only. While a settings question is open, a button under an older alert answers "Finish or cancel the
  settings question first."
- **An old button.** A button from an earlier card, or one forwarded from another chat, changes nothing. The bot says
  "That card is out of date." and offers Show settings.
- **Changed elsewhere.** If the stored settings changed between showing the card and your answer, nothing is saved.
  The bot says so and shows the current values.
- **Save failed.** If the assistant cannot save, the bot says "I could not save that. Nothing was changed. Try again
  in a moment." with a Show settings button.

## When the saved settings are missing or invalid

- **Nothing saved yet.** The assistant works with the default values listed above.
- **Saved settings cannot be used.** If the saved settings are invalid, or cannot be read within 2 seconds, the
  assistant keeps alerting. It uses the last good values it knew, or the defaults if there were none, and sends you one
  Telegram message per incident: "I cannot use your saved settings (...). Until that is fixed I am using:" followed by
  the four values in use. When the settings can be read again, a later problem gets its own message.
- **Repair from Telegram.** While the saved settings are invalid, `/settings` still opens. It shows the values in use
  with a note that the saved settings are not valid. Change any one value and the assistant saves all four as a new
  set.

## Not included yet

- A web page for the settings is a separate, later feature (`web-settings`). It does not exist yet, and nothing on
  this page needs it.
- There is no automatic detection of your location and no separate schedule per weekday.

## Related pages

- [Quiet hours specification](../specs/adjustable-quiet-hours.md)
- [Mail triage specification](../specs/mail-triage.md)
