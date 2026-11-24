from category_policy import DECISIONS, RESERVED_NAMES, label_for


def test_given_a_name_when_mapped_to_a_label_then_the_label_is_the_name():
    assert label_for("Invoices") == "Invoices"


def test_given_the_reserved_names_when_read_then_they_are_other_and_archive():
    assert sorted(RESERVED_NAMES) == ["archive", "other"]


def test_given_the_decisions_when_read_then_they_are_the_plan_item_values():
    assert DECISIONS == ("pending", "approved", "rejected")
