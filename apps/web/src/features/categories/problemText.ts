/** One refused rule in plain words; the rule ids are those of `category-policy`. */
const TEXT: Record<string, string> = {
  name_empty: "Give the category a name.",
  name_segment_empty: "Every part of a name needs text. Remove the extra slash or fill the empty part.",
  name_segment_too_long: "Use at most 40 characters for each part of the name.",
  name_label_too_long: "This name is too long for a Gmail label. Use at most 255 characters in total.",
  name_forbidden_char: "A name cannot contain control or invisible characters.",
  name_reserved: "This name is kept for the assistant or Gmail. The first part cannot be Archive or Other, and Gmail's own labels like Inbox are not allowed.",
  name_duplicate: "Another category already has this name.",
  name_setting_clash: "This name is already used for your Other or archive label. Choose another name.",
  description_empty: "Say what belongs in this category.",
  description_too_long: "Use at most 1500 characters for the description.",
  instructions_too_long: "Use at most 4000 characters for the general instructions.",
  sender_invalid: "This is not a valid address or domain.",
  sender_refused_domain: "A whole domain like this cannot be listed. Use full addresses instead.",
  setting_name_invalid: "This is not a valid label name.",
  setting_name_too_long: "Use at most 255 characters for the label name.",
  setting_name_system_label: "This is a Gmail label of its own and cannot be used here.",
  setting_name_reserved: "This name is kept for the assistant, or the other setting already uses it. Choose another name.",
  setting_name_category_clash: "A category already uses this label, or lies below it. Choose another name.",
  sender_too_many: "A category can list at most 100 senders.",
};

/** A rule this page does not know gets a generic sentence, so a new rule on the server is never a bare code. */
export function problemText(rule: string): string {
  return TEXT[rule] ?? "That is not allowed.";
}
