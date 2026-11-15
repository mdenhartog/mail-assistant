/** One refused rule in plain words; the rule ids are those of `category-policy`. */
const TEXT: Record<string, string> = {
  name_empty: "Give the category a name.",
  name_too_long: "Use at most 40 characters for the name.",
  name_slash: "A name cannot contain a slash.",
  name_forbidden_char: "A name cannot contain control or invisible characters.",
  name_reserved: "That name is kept for the assistant. Pick another.",
  name_duplicate: "Another category already has this name.",
  name_label_exists: "A Gmail label with this name already exists.",
  description_empty: "Say what belongs in this category.",
  description_too_long: "Use at most 500 characters for the description.",
};

/** A rule this page does not know gets a generic sentence, so a new rule on the server is never a bare code. */
export function problemText(rule: string): string {
  return TEXT[rule] ?? "That is not allowed.";
}
