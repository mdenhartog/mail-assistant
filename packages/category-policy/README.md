# category-policy

Shared Python package for the category contract, version 2 (INT-008, ADR-0053, ADR-0059). Rebuilt from the INT-004 version: names nest with `/` and the rules apply per segment, kinds (`topic`, `extra`), the limits (segment 40, label 225, description 1 500, general instructions 4 000, 100 categories), the archive label rule, the one confidence scale, the `Assistant/` label mapping, plan decision values and a shared contract-case file used by the mail-triage agent and the api.

Status: U-label-structure-02 (names, kinds, limits, archive label, confidence scale) and U-label-structure-03 (sender entries, the matcher, the refused domain lists) built. The YAML schema follows in a later unit. Run the tests with `uv run pytest` in this folder.

## Using it

- `validate_category(name, description, existing, labels, adoptable)` returns the problems in rule order, or an empty list. `labels` are the Gmail labels that exist; `adoptable` is the subset of them that belongs to an older category, so a new category of that name adopts the label and its mail instead of clashing. The caller works out `adoptable`; the package does not read Gmail.
- `validate_list(categories, labels, adoptable)` checks every category and the cap; `validate_instructions(text)` the general instructions.
- `validate_archive_label(name, categories)` reports one problem (`archive_invalid`, `archive_system_label`, `archive_category_label`, `archive_inside_assistant`) or none.
- `confidence_pct(confidence)` rounds half up to whole percent; `at_or_above(pct, threshold)` is the "at or above" comparison.
- `parse_entry(text, subdomains)` returns the entry in stored form (lower-case A-label, lower-case address) or None; patterns, bare names, look-alikes the IDNA mapping would fold (full-width letters) and an opt-in on an address are refused.
- `build_matcher(categories)` returns `match(from_header) -> Match | None` with a topic hit and an extra-label hit, each by its longest entry (exact address, then the domain and, with `subdomains`, its suffixes at a dot boundary). A missing, several or unparsable `From` matches nothing. `validate_entries(categories)` reports `SENDER_RULES` problems (at most 100 entries, valid, not a refused domain, an entry in one topic and one extra category). `REFUSED_DOMAINS` (public mailbox providers and multi-tenant sending platforms, subdomains included) apply to domain entries only; `oma@gmail.com` stays allowed.
- `contract/sender_cases.json` holds the shared sender cases.
- `contract/category_cases.json` holds the shared cases; its `description` explains the row formats.

Nightly mutation testing of `policy.py` runs in `.github/workflows/mutation.yml` (job `category-policy`, at least 85 %).
