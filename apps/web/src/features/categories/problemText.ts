/** One refused rule in plain words; the rule ids are those of `category-policy`. */
const TEXT: Record<string, string> = {
  name_empty: "Give the category a name.",
  name_segment_empty: "Every part of a name needs text. Remove the extra slash or fill the empty part.",
  name_segment_too_long: "Use at most 40 characters for each part of the name.",
  name_label_too_long: "This name is too long for a Gmail label. Use at most 225 characters in total, including the Assistant/ prefix.",
  name_forbidden_char: "A name cannot contain control or invisible characters.",
  name_reserved: "The first part of a name cannot be Archive or Other. Those are kept for the assistant.",
  name_duplicate: "Another category already has this name.",
  name_label_exists: "A Gmail label with this name already exists.",
  description_empty: "Say what belongs in this category.",
  description_too_long: "Use at most 1500 characters for the description.",
  instructions_too_long: "Use at most 4000 characters for the general instructions.",
  sender_invalid: "This is not a valid address or domain.",
  sender_refused_domain: "A whole domain like this cannot be listed. Use full addresses instead.",
  sender_too_many: "A category can list at most 100 senders.",
};

/** A rule this page does not know gets a generic sentence, so a new rule on the server is never a bare code. */
export function problemText(rule: string): string {
  return TEXT[rule] ?? "That is not allowed.";
}
