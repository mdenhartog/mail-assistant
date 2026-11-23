"""The YAML category file: parser, export, template and fixtures (INT-008, C-7, C-8, D6, D20, D21, AC-32 to AC-39)."""

import json
from pathlib import Path

import pytest

from category_policy import (
    MAX_CATEGORIES,
    RULES,
    SENDER_RULES,
    Kind,
    SenderEntry,
)
from category_policy.yaml_file import (
    FILE_RULE_TEXT,
    MAX_FILE_BYTES,
    FileCategory,
    FileProblem,
    FileProblems,
    ParsedList,
    dump_category_file,
    parse_category_file,
)

PACKAGE = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
CANARY = "CANARY-7f3a"


def load(path: Path) -> bytes:
    return path.read_bytes()


def as_bytes(data: bytes | str) -> bytes:
    return data if isinstance(data, bytes) else data.encode()


def parsed(data: bytes | str) -> ParsedList:
    result = parse_category_file(as_bytes(data))
    assert isinstance(result, ParsedList), result
    return result


def problems_of(data: bytes | str) -> list[FileProblem]:
    result = parse_category_file(as_bytes(data))
    assert isinstance(result, FileProblems), result
    return list(result.problems)


def rules(data: bytes | str) -> list[str]:
    return [problem.rule for problem in problems_of(data)]


def doc(body: str) -> str:
    return f"schema: 1\n{body}"


def pairs(data: bytes | str) -> list[tuple[str, str]]:
    return [(p.rule, p.field) for p in problems_of(data)]


EXPECTED_SMALL = ParsedList(
    general_instructions="Mail from the school is always important.",
    archive_label="Assistant/Archive",
    categories=(
        FileCategory(
            name="Huis/Energie",
            kind=Kind.TOPIC,
            description="Energy contracts, meter readings and yearly statements.",
            senders=(
                SenderEntry("energie.example.com", False),
                SenderEntry("example.org", True),
                SenderEntry("billing@example.net", False),
            ),
            notify=True,
        ),
        FileCategory(
            name="Facturen",
            kind=Kind.EXTRA,
            description="Any invoice or payment request, whatever the topic.",
        ),
        FileCategory(
            name="no",
            description="A name that must stay a string.",
            senders=(SenderEntry("on.example.com", False),),
        ),
    ),
)


# Criterion 1: a valid file parses to the expected list and survives a dump and a parse.
def test_given_a_valid_file_when_parsed_then_the_list_is_the_expected_one():
    assert parsed(load(FIXTURES / "valid" / "small.yaml")) == EXPECTED_SMALL


def test_given_a_file_with_and_without_an_archive_label_when_parsed_then_it_says_whether_it_was_given():
    absent = parse_category_file(as_bytes(doc("categories: []")))
    given = parse_category_file(as_bytes(doc("archiveLabel: Assistant/Archive\ncategories: []")))

    assert isinstance(absent, ParsedList)
    assert isinstance(given, ParsedList)
    assert (absent.archive_label_given, given.archive_label_given) == (False, True)


def test_given_a_parsed_list_when_dumped_and_parsed_again_then_the_list_is_the_same():
    assert parsed(dump_category_file(EXPECTED_SMALL)) == EXPECTED_SMALL


def test_given_a_crlf_file_when_parsed_then_it_is_accepted():
    result = parsed(load(FIXTURES / "valid" / "crlf.yaml"))

    assert [c.name for c in result.categories] == ["Huis"]


def test_given_only_the_required_fields_when_parsed_then_the_defaults_apply():
    result = parsed(doc("categories:\n  - name: Huis\n    description: A\n"))

    assert result == ParsedList(
        general_instructions="",
        archive_label="Assistant/Archive",
        categories=(FileCategory(name="Huis", description="A"),),
    )


def test_given_an_exported_file_when_inspected_then_it_carries_schema_1_and_is_utf8():
    data = dump_category_file(EXPECTED_SMALL)

    assert b"schema: 1" in data
    assert data.decode("utf-8")


def test_given_hard_to_write_text_when_dumped_and_parsed_then_it_round_trips():
    nasty = ParsedList(
        general_instructions="line one\nline two: with colon # and hash\n\ttabbed",
        archive_label="Archive",
        categories=(
            FileCategory(
                name="yes",
                description="true",
                senders=(SenderEntry("null.example.com", False),),
                notify=False,
            ),
            FileCategory(name="Café/Ünï", description="- starts with a dash\x00and a nul﻿", kind=Kind.EXTRA),
        ),
    )

    assert parsed(dump_category_file(nasty)) == nasty


# Criterion 2: hostile files give every problem with line and field, and nothing is built.
@pytest.mark.parametrize(
    ("fixture", "rule", "line", "field"),
    [
        ("anchor.yaml", "anchor", 3, "categories[0].name"),
        ("alias.yaml", "alias", 6, "categories[1].description"),
        ("merge_key.yaml", "merge_key", 6, "categories[1]"),
        ("merge_key_only.yaml", "merge_key", 5, "categories[0]"),
        ("python_object.yaml", "tag", 3, "categories[0].name"),
        ("explicit_tag.yaml", "tag", 3, "categories[0].name"),
        ("duplicate_keys.yaml", "duplicate_key", 5, "categories[0]"),
        ("tabs.yaml", "tab", 3, "file"),
        ("bom.yaml", "bom", 1, "file"),
        ("nul_byte.yaml", "nul_byte", 3, "file"),
        ("not_yaml.yaml", "syntax", 2, "file"),
    ],
)
def test_given_a_hostile_file_when_parsed_then_the_problem_has_rule_line_and_field(
    fixture: str, rule: str, line: int, field: str
):
    found = problems_of(load(FIXTURES / "hostile" / fixture))

    assert FileProblem(rule, line, field) in found


def test_given_a_file_with_unknown_fields_when_parsed_then_every_unknown_field_is_listed():
    found = problems_of(load(FIXTURES / "hostile" / "unknown_field.yaml"))

    assert [(p.rule, p.line, p.field) for p in found] == [
        ("unknown_field", 2, "root"),
        ("unknown_field", 6, "categories[0]"),
    ]


def test_given_a_billion_laughs_file_when_parsed_then_every_alias_is_refused_without_expanding():
    found = problems_of(load(FIXTURES / "hostile" / "billion_laughs.yaml"))

    assert {p.rule for p in found} >= {"anchor", "alias"}


def test_given_a_file_over_256_kib_when_parsed_then_it_is_refused_before_parsing():
    data = b"schema: 1\n" + b"# " + b"x" * MAX_FILE_BYTES + b"\n"

    assert problems_of(data) == [FileProblem("file_too_large", 1, "file")]


def test_given_a_file_of_exactly_256_kib_when_parsed_then_the_size_is_accepted():
    body = b"schema: 1\ncategories:\n  - name: Huis\n    description: A\n"
    data = body + b"#" * (MAX_FILE_BYTES - len(body) - 1) + b"\n"

    assert len(data) == MAX_FILE_BYTES
    assert isinstance(parse_category_file(data), ParsedList)


@pytest.mark.parametrize("opener", ["[", "{a: "])
def test_given_nesting_1000_deep_when_parsed_then_it_is_refused_as_too_deep(opener: str):
    closer = "]" if opener == "[" else "}"
    text = doc("categories: " + opener * 1000 + "x" + closer * 1000 + "\n")

    assert "too_deep" in rules(text)


def test_given_block_nesting_600_deep_when_parsed_then_it_is_refused_as_too_deep():
    text = "schema: 1\ncategories:\n" + "".join(f"{' ' * (i + 1)}- \n" for i in range(600))

    assert "too_deep" in rules(text)


def test_given_more_nodes_than_the_limit_when_parsed_then_it_is_refused():
    text = doc("categories: [" + ",".join(["a"] * 60_000) + "]\n")

    assert rules(text) == ["too_many_nodes"]


def test_given_thousands_of_violations_when_parsed_then_the_list_of_problems_is_capped():
    text = doc("categories:\n" + "  - &a x\n" * 5000)

    found = rules(text)

    assert len(found) <= 101
    assert found[-1] == "too_many_problems"


def test_given_invalid_utf8_when_parsed_then_it_is_a_problem_not_an_exception():
    assert rules(b"schema: 1\n\xff\xfe\n") == ["not_utf8"]


@pytest.mark.parametrize("text", ["", "# only a comment\n", "   \n"])
def test_given_an_empty_file_when_parsed_then_it_is_refused(text: str):
    assert rules(text) == ["empty_file"]


def test_given_two_documents_when_parsed_then_it_is_refused():
    assert "multiple_documents" in rules(doc("categories: []\n---\nschema: 1\n"))


@pytest.mark.parametrize("text", ["just text\n", "- a\n- b\n"])
def test_given_a_file_that_is_not_a_mapping_when_parsed_then_it_is_refused(text: str):
    assert rules(text) == ["not_mapping"]


def test_given_a_complex_key_when_parsed_then_it_is_refused():
    assert "key_not_text" in rules(doc("? [a, b]\n: c\ncategories: []\n"))


def test_given_bad_content_when_parsed_then_no_list_is_returned():
    assert isinstance(parse_category_file(b"schema: 2\ncategories: []\n"), FileProblems)


# Criterion 3: YAML 1.1 words stay strings or are refused, never booleans.
@pytest.mark.parametrize("word", ["no", "on", "yes", "off", "true", "null", "NO", "y", "n"])
def test_given_a_yaml_boolean_word_as_a_name_when_parsed_then_it_stays_a_string(word: str):
    result = parsed(doc(f"categories:\n  - name: {word}\n    description: A\n"))

    assert result.categories[0].name == word


@pytest.mark.parametrize("word", ["no", "on", "yes", "True"])
def test_given_a_yaml_boolean_word_as_a_sender_when_parsed_then_it_is_a_string_the_policy_refuses(word: str):
    found = pairs(doc(f"categories:\n  - name: Huis\n    description: A\n    senders:\n      - {word}\n"))

    assert found == [("sender_invalid", "categories[0].senders[0]")]


@pytest.mark.parametrize("word", ["yes", "no", "on", "True", "1", "'true'"])
def test_given_a_yaml_boolean_word_for_notify_when_parsed_then_it_is_refused_not_converted(word: str):
    found = pairs(doc(f"categories:\n  - name: Huis\n    description: A\n    notify: {word}\n"))

    assert found == [("not_boolean", "categories[0].notify")]


def test_given_a_yaml_boolean_word_for_subdomains_when_parsed_then_it_is_refused():
    body = (
        "categories:\n  - name: Huis\n    description: A\n    senders:\n"
        "      - entry: example.org\n        subdomains: yes\n"
    )

    assert pairs(doc(body)) == [("not_boolean", "categories[0].senders[0].subdomains")]


def test_given_numbers_for_text_when_parsed_then_they_stay_text():
    result = parsed(doc("categories:\n  - name: 2024\n    description: ~\n"))

    assert (result.categories[0].name, result.categories[0].description) == ("2024", "~")


# Structure rules.
@pytest.mark.parametrize("head", ["schema: 2\n", "schema: '1'\n", "schema: yes\n", "schema: 1.0\n", ""])
def test_given_another_or_missing_schema_when_parsed_then_it_is_refused(head: str):
    found = problems_of(head + "categories: []\n")

    assert [p.rule for p in found] == ["schema_unsupported" if head else "missing_field"]
    assert found[0].field == "schema"


def test_given_no_categories_key_when_parsed_then_it_is_a_missing_field():
    assert pairs("schema: 1\n") == [("missing_field", "categories")]


@pytest.mark.parametrize(
    ("body", "rule", "field"),
    [
        ("categories: text\n", "not_list", "categories"),
        ("categories:\n  - text\n", "not_map", "categories[0]"),
        ("categories:\n  - name: [a]\n    description: A\n", "not_text", "categories[0].name"),
        ("categories:\n  - name: Huis\n    description: {a: b}\n", "not_text", "categories[0].description"),
        ("categories:\n  - name: Huis\n    description: A\n    kind: other\n", "kind_invalid", "categories[0].kind"),
        ("categories:\n  - name: Huis\n    description: A\n    senders: x\n", "not_list", "categories[0].senders"),
        (
            "categories:\n  - name: Huis\n    description: A\n    senders: [[a]]\n",
            "not_text",
            "categories[0].senders[0]",
        ),
        (
            "categories:\n  - name: Huis\n    description: A\n    senders:\n      - subdomains: true\n",
            "missing_field",
            "categories[0].senders[0]",
        ),
        (
            "categories:\n  - name: Huis\n    description: A\n    senders:\n"
            "      - entry: a.example.com\n        x: 1\n",
            "unknown_field",
            "categories[0].senders[0]",
        ),
        ("generalInstructions: [a]\ncategories: []\n", "not_text", "generalInstructions"),
        ("archiveLabel: [a]\ncategories: []\n", "not_text", "archiveLabel"),
    ],
)
def test_given_a_structural_mistake_when_parsed_then_the_problem_names_rule_and_field(body: str, rule: str, field: str):
    assert (rule, field) in pairs(doc(body))


def test_given_several_structural_mistakes_when_parsed_then_all_are_listed_with_their_lines():
    body = (
        "categories:\n"  # 2
        "  - name: [a]\n"  # 3
        "    description: A\n"  # 4
        "  - name: Auto\n"  # 5
        "    kind: nope\n"  # 6
        "    notify: maybe\n"  # 7
    )

    found = problems_of(doc(body))

    assert [(p.rule, p.line, p.field) for p in found] == [
        ("not_text", 3, "categories[0].name"),
        ("missing_field", 5, "categories[1].description"),
        ("kind_invalid", 6, "categories[1].kind"),
        ("not_boolean", 7, "categories[1].notify"),
    ]


# Every rule of the policy comes through the policy functions, with line and field.
def test_given_policy_violations_when_parsed_then_each_is_reported_with_line_and_field():
    body = (
        "generalInstructions: " + "x" * 4001 + "\n"  # 2
        "archiveLabel: Assistant/Mail\n"  # 3
        "categories:\n"  # 4
        "  - name: Other\n"  # 5
        "    description: A\n"  # 6
        "  - name: Huis\n"  # 7
        "    description: ''\n"  # 8
        "    senders:\n"  # 9
        "      - gmail.com\n"  # 10
        "      - not a domain\n"  # 11
        "      - example.org\n"  # 12
        "  - name: huis\n"  # 13
        "    description: B\n"  # 14
        "    senders: [example.org]\n"  # 15
    )

    found = problems_of(doc(body))

    assert [(p.rule, p.line, p.field) for p in found] == [
        ("instructions_too_long", 2, "generalInstructions"),
        ("archive_inside_assistant", 3, "archiveLabel"),
        ("name_reserved", 5, "categories[0].name"),
        ("description_empty", 8, "categories[1].description"),
        ("sender_refused_domain", 10, "categories[1].senders[0]"),
        ("sender_invalid", 11, "categories[1].senders[1]"),
        ("name_duplicate", 13, "categories[2].name"),
        ("sender_duplicate", 15, "categories[2].senders[0]"),
    ]


def test_given_more_than_the_maximum_categories_when_parsed_then_the_list_is_refused():
    body = "categories:\n" + "".join(f"  - name: C{i}\n    description: A\n" for i in range(MAX_CATEGORIES + 1))

    assert pairs(doc(body)) == [("list_too_many", "categories")]


def test_given_a_category_with_too_many_senders_when_parsed_then_it_is_refused():
    senders = "".join(f"      - s{i}.example.com\n" for i in range(101))

    found = pairs(doc(f"categories:\n  - name: Huis\n    description: A\n    senders:\n{senders}"))

    assert found == [("sender_too_many", "categories[0].senders")]


def test_given_a_subdomain_flag_on_an_address_when_parsed_then_it_is_refused_by_the_policy():
    body = (
        "categories:\n  - name: Huis\n    description: A\n    senders:\n"
        "      - {entry: a@example.org, subdomains: true}\n"
    )

    assert pairs(doc(body)) == [("sender_invalid", "categories[0].senders[0]")]


def test_given_the_archive_label_below_a_category_label_when_parsed_then_it_is_refused():
    body = "archiveLabel: Assistant/Huis\ncategories:\n  - name: Huis\n    description: A\n"

    assert pairs(doc(body)) == [("archive_category_label", "archiveLabel")]


def test_given_a_name_that_is_a_gmail_system_label_for_the_archive_when_parsed_then_it_is_refused():
    body = "archiveLabel: INBOX\ncategories:\n  - name: Huis\n    description: A\n"

    assert pairs(doc(body)) == [("archive_system_label", "archiveLabel")]


# Criterion 4: the anonymised golden file.
def test_given_the_golden_file_when_parsed_then_it_has_43_categories_that_equal_the_signed_off_choices():
    expected = json.loads((FIXTURES / "golden_example_43.expected.json").read_text(encoding="utf-8"))

    result = parsed(load(FIXTURES / "golden_example_43.yaml"))

    assert len(result.categories) == 43
    assert result.general_instructions == expected["generalInstructions"]
    assert result.archive_label == expected["archiveLabel"]
    actual = [(c.name, c.kind.value, c.notify, len(c.senders)) for c in result.categories]
    assert actual == [(e["name"], e["kind"], e["notify"], e["senders"]) for e in expected["categories"]]
    lossy = {e["name"] for e in expected["categories"] if e["meaningLost"]}
    assert lossy
    for category in result.categories:
        assert category.description.strip()
        assert ("Meaning lost" in category.description) == (category.name in lossy)


def test_given_the_golden_file_when_inspected_then_it_has_nested_names_one_extra_and_only_example_domains():
    result = parsed(load(FIXTURES / "golden_example_43.yaml"))

    names = [c.name for c in result.categories]
    assert "Huis/Energie" in names
    assert "Chalet/Camping" in names
    assert [c.name for c in result.categories if c.kind is Kind.EXTRA] == ["Facturen"]
    for category in result.categories:
        for sender in category.senders:
            domain = sender.text.rpartition("@")[2]
            assert domain.endswith(("example.com", "example.org", "example.net")), domain


def test_given_the_golden_file_when_dumped_and_parsed_then_the_list_is_unchanged():
    result = parsed(load(FIXTURES / "golden_example_43.yaml"))

    assert parsed(dump_category_file(result)) == result


# Criterion 5: template and example.
TEMPLATE_FILES = ["mail-categories.template.yaml", "mail-categories.example.yaml"]


@pytest.mark.parametrize("name", TEMPLATE_FILES)
def test_given_the_template_and_the_example_when_parsed_then_both_pass(name: str):
    assert parsed(load(PACKAGE / "template" / name)).categories


@pytest.mark.parametrize("name", TEMPLATE_FILES)
def test_given_the_template_and_the_example_when_read_then_every_field_of_the_format_is_explained(name: str):
    lines = (PACKAGE / "template" / name).read_text(encoding="utf-8").splitlines()
    comments = "\n".join(line[line.index("#") :] for line in lines if "#" in line)

    for field in (
        "schema",
        "generalInstructions",
        "archiveLabel",
        "categories",
        "name",
        "kind",
        "topic",
        "extra",
        "description",
        "senders",
        "entry",
        "subdomains",
        "notify",
    ):
        assert field in comments, field


def test_given_the_template_when_parsed_then_it_has_a_topic_an_extra_a_subdomain_sender_and_a_tick():
    result = parsed(load(PACKAGE / "template" / "mail-categories.template.yaml"))

    assert {c.kind for c in result.categories} == {Kind.TOPIC, Kind.EXTRA}
    assert any(c.notify for c in result.categories)
    assert any(s.subdomains for c in result.categories for s in c.senders)
    assert result.general_instructions


@pytest.mark.parametrize("name", TEMPLATE_FILES)
def test_given_the_template_and_the_example_when_read_then_they_hold_no_tab_and_no_bom(name: str):
    data = (PACKAGE / "template" / name).read_bytes()

    assert b"\t" not in data
    assert not data.startswith(b"\xef\xbb\xbf")


# Criterion 6: a message names field and place and never the value.
HOSTILE_VALUES = [
    f"name: {CANARY}\n    description: ''\n",
    f"name: &x {CANARY}\n    description: A\n",
    f"name: !!python/object:{CANARY} x\n    description: A\n",
    f"name: {CANARY}\n    description: A\n    kind: {CANARY}\n",
    f"name: {CANARY}\n    description: A\n    notify: {CANARY}\n",
    f"name: {CANARY}\n    description: A\n    {CANARY}: 1\n",
    f"name: {CANARY}\n    description: A\n    senders: [{CANARY}, {CANARY}.example.com, {CANARY}.gmail.com]\n",
    f"name: Other\n    description: {CANARY}\n    senders: [{CANARY}]\n",
]


@pytest.mark.parametrize("item", HOSTILE_VALUES)
def test_given_any_problem_when_reported_then_no_message_contains_the_value(item: str):
    text = f"schema: 1\ngeneralInstructions: {CANARY}\narchiveLabel: Assistant/{CANARY}\ncategories:\n  - {item}"

    result = parse_category_file(text.encode())

    assert isinstance(result, FileProblems)
    assert result.problems
    for problem in result.problems:
        assert CANARY not in str(problem)
        assert CANARY not in repr(problem)
    assert CANARY not in str(result)


def test_given_a_problem_when_formatted_then_the_message_reads_line_field_and_a_fixed_text():
    problem = FileProblem("sender_invalid", 12, "categories[0].senders[3]")

    assert str(problem) == f"line 12, categories[0].senders[3]: {FILE_RULE_TEXT['sender_invalid']}"


def test_given_every_policy_rule_when_listed_then_each_has_a_fixed_text():
    assert {*RULES, *SENDER_RULES} <= set(FILE_RULE_TEXT)
    assert all(text and CANARY not in text for text in FILE_RULE_TEXT.values())


def test_given_a_control_character_when_parsed_then_it_is_a_syntax_problem_with_its_line():
    assert problems_of("schema: 1\ncategories:\n  - name: a\x07b\n") == [FileProblem("syntax", 3, "file")]


def test_given_a_category_without_a_name_when_parsed_then_the_missing_field_is_reported_once():
    assert pairs(doc("categories:\n  - description: A\n")) == [("missing_field", "categories[0].name")]
