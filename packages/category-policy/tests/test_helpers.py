from category_policy import DECISIONS, label_for


def test_given_a_name_when_mapped_to_a_label_then_it_sits_under_assistant():
    assert label_for("Invoices") == "Assistant/Invoices"


def test_given_a_padded_name_when_mapped_then_the_label_uses_the_trimmed_name():
    assert label_for("  Invoices ") == "Assistant/Invoices"


def test_given_the_decisions_when_read_then_they_are_the_plan_item_values():
    assert DECISIONS == ("pending", "approved", "rejected")
