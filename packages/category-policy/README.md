# category-policy

Shared Python package for the category contract of `mail-categories` (INT-004, ADR-0042): name rules, limits, reserved names, the `Assistant/` label mapping, plan decision values and a shared contract-case file, used by the mail-triage agent and the api.

Status: built (U-mail-categories-02). Run the tests with `uv run pytest` in this folder.

## Using it

`validate_category(name, description, existing, labels, adoptable)` returns the problems in rule order, or an empty list. `labels` are the Gmail labels that exist; `adoptable` is the subset of them that belongs to an older category, so a new category of that name adopts the label and its mail instead of clashing (AC-53). The caller works out `adoptable` (an `Assistant/` label that is not on the stored list and whose suffix is not reserved); the package does not read Gmail. Nightly mutation testing of `policy.py` runs in `.github/workflows/mutation.yml` (job `category-policy`, at least 85 %).
