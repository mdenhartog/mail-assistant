from category_policy import DECISIONS, LABEL_PREFIX, RESERVED_NAMES, label_for


def test_given_a_name_when_mapped_to_a_label_then_it_sits_under_assistant():
    assert label_for("Invoices") == "Assistant/Invoices"
    assert LABEL_PREFIX == "Assistant/"


def test_given_the_reserved_names_when_read_then_they_are_other_and_archive():
    assert sorted(RESERVED_NAMES) == ["archive", "other"]


def test_given_the_decisions_when_read_then_they_are_the_plan_item_values():
    assert DECISIONS == ("pending", "approved", "rejected")
