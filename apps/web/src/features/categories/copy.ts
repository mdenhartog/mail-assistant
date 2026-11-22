/** "1 mail", "12 mails". */
export function countText(count: number): string {
  return `${String(count)} ${count === 1 ? "mail" : "mails"}`;
}

/** "No senders", "1 sender", "37 senders". */
export function sendersCountText(count: number): string {
  if (count === 0) {
    return "No senders";
  }
  return `${String(count)} ${count === 1 ? "sender" : "senders"}`;
}

/**
 * The help beside the fields of the edit view. The first four sentences are worded by the spec (Screens), so
 * they are used literally; the rest says how to write the entries and what the list's instructions are.
 */
export const HELP = {
  name: "Use a slash to nest a category under another one: Huis/Energie sits under Huis.",
  topic: "Every mail gets exactly one. If nothing fits, it goes to Other.",
  extra: "Added on top of the topic, at most one per mail.",
  description: "The model reads the description. Say what belongs here, for example: Invoices, receipts and payment confirmations.",
  senders:
    "Mail from these addresses or domains goes here without the AI choosing the category, only when Gmail confirms the sender is real. If Gmail cannot confirm it, the mail goes to the AI.",
  sendersFormat:
    "One entry per line: an address such as billing@example.com or a domain such as example.com. Write +subdomains after a domain to include its subdomains too, for example: example.com +subdomains.",
  notify: "You get a Telegram message for every new mail here, urgent or not.",
  notifyCap: "Alerts are limited per hour; the ones above the limit are sent together.",
  instructions:
    "Tell the AI anything that applies to the whole list, for example how to treat mail in another language. It reads this text together with the descriptions; it cannot change the rules of the app.",
} as const;

/** "Not applied 3 times: Gmail could not confirm the sender"; a count and a fixed text, never mail content. */
export function skippedText(count: number): string {
  return `Not applied ${String(count)} ${count === 1 ? "time" : "times"}: Gmail could not confirm the sender`;
}

/** Said once under the Senders field when any entry has a skipped count. */
export const SKIPPED_NOTE = "The AI judged those mails instead.";

/** The fixed block of the Categories page (Screens). */
export const FIXED_BLOCK =
  "Changing the list never moves mail you already have. Only new mail follows it. To re-sort the inbox, press Sort everything again.";
