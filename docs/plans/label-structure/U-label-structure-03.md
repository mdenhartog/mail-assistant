---
intent: INT-008
feature: label-structure
---

# U-label-structure-03: category-policy v2: sender entries, the matcher and the refused domains

- Component: category-policy
- Layer: backend
- Contract: `parse_entry(text, subdomains)` (address or domain, lower-case A-label), `build_matcher(categories)` returning `match(from_address) -> Match | None` (exact address, then domain suffixes at a dot boundary, `subdomains: true` opt-in, longest wins), `validate_entries(categories)` (at most 100 per category, an entry in at most one topic and one extra-label category), `REFUSED_DOMAINS` (public mailbox providers, multi-tenant sending platforms) for domain entries only.
- Files: `packages/category-policy/category_policy/senders.py`, `packages/category-policy/category_policy/refused_domains.py`, contract cases, tests in `packages/category-policy/tests/`
- Depends on: U-label-structure-02
- Parallel: yes
- Guardrails: guardrail-python, guardrail-pytest
- Criteria:
  1. Given an address entry and a domain entry that both match, When matched, Then the longest wins. (type: happy)
  2. Given a domain entry without `subdomains: true`, When a subdomain sender is matched, Then it does not match; with `subdomains: true` it matches at a dot boundary only. (type: edge)
  3. Given `evil-example.nl`, `example.nl.evil.com`, an IDN look-alike and a missing, several or unparsable `From`, When matched against `example.nl`, Then none matches. (type: security)
  4. Given the same entry (also case-folded or punycode-equal) in two topic categories or two extra-label categories, When validated, Then it is refused naming both. (type: error)
  5. Given a domain entry for a public mailbox provider or a multi-tenant sending platform, When validated, Then it is refused; Given a full address on that domain, Then it is accepted. (type: security)
  6. Given 100 categories with 100 entries each, When the matcher is built and used, Then matching one mail stays within a fixed time bound; a property test shows no entry makes it slower (no patterns). (type: edge)
