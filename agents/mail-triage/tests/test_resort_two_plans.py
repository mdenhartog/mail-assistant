"""U-label-structure-23, criteria 1 and 5: one build, two plans (ADR-0056 point 2; spec C-14, AC-9)."""

from __future__ import annotations

from app.core.judgement import ListedCategory
from app.core.resort_plan import PlanState
from app.usecases.resort_build import BuildStatus
from category_policy.kinds import Kind
from category_policy.senders import SenderEntry
from tests.resort_build_support import FINANCE, TRAVEL, Rig

BANK = "00000000-0000-0000-0000-0000000000b1"
AUTH = "mx.google.com; dmarc=pass header.from=bank.example.test"


def _subjects(items: list) -> set[str]:  # type: ignore[type-arg]
    return {i.subject for i in items}


async def _three_mails(threshold: int) -> Rig:
    rig = Rig()
    rig.request(threshold)
    for subject in ("m95", "m80", "m79"):
        rig.gmail.add_mail(("INBOX", rig.travel_label), subject=subject)
    rig.judge.answers = {"m95": (FINANCE, None, 0.95), "m80": (FINANCE, None, 0.80), "m79": (FINANCE, None, 0.79)}
    return rig


async def test_given_confidence_95_80_and_79_at_threshold_80_when_built_then_two_are_auto_and_one_is_review() -> None:
    rig = await _three_mails(80)

    result = await rig.build.run_once()

    plan = rig.store.plan()
    assert result.status is BuildStatus.READY
    assert _subjects(rig.store.auto_items_of(plan)) == {"m95", "m80"}
    assert _subjects(rig.store.review_items_of(plan)) == {"m79"}
    assert result.numbers is not None
    assert (result.numbers.to_move, result.numbers.to_review) == (2, 1)


async def test_given_threshold_96_when_built_then_only_a_sender_rule_item_is_auto() -> None:
    rig = Rig()
    rig.store.save_list(
        (
            ListedCategory(FINANCE, "Finance", "Bills"),
            ListedCategory(TRAVEL, "Travel", "Tickets"),
            ListedCategory(BANK, "Bank", "The bank", Kind.TOPIC, False, (SenderEntry("bank.example.test"),)),
        )
    )
    rig.request(96)
    rig.gmail.add_mail(("INBOX",), sender="bills@bank.example.test", subject="rule", auth_results=AUTH)
    rig.gmail.add_mail(("INBOX",), subject="model")
    rig.judge.answers = {"model": (FINANCE, None, 0.95)}

    await rig.build.run_once()

    plan = rig.store.plan()
    assert _subjects(rig.store.auto_items_of(plan)) == {"rule"}
    assert _subjects(rig.store.review_items_of(plan)) == {"model"}


async def test_given_threshold_100_when_built_then_only_confidence_100_is_auto() -> None:
    rig = Rig()
    rig.request(100)
    rig.gmail.add_mail(("INBOX",), subject="sure")
    rig.gmail.add_mail(("INBOX",), subject="almost")
    rig.judge.answers = {"sure": (FINANCE, None, 1.0), "almost": (FINANCE, None, 0.99)}

    await rig.build.run_once()

    plan = rig.store.plan()
    assert _subjects(rig.store.auto_items_of(plan)) == {"sure"}
    assert _subjects(rig.store.review_items_of(plan)) == {"almost"}


async def test_given_a_ready_build_when_it_ends_then_the_auto_plan_is_approved_and_the_review_plan_waits() -> None:
    rig = await _three_mails(80)

    await rig.build.run_once()

    plan = rig.store.plan()
    assert rig.store.auto_state[plan.plan_id] is PlanState.SCHEDULED  # approved by the agent through the threshold
    assert plan.state is PlanState.READY  # the review plan waits for the user
    assert rig.gmail.mail_table  # and nothing moved
    assert all(m.labels == {"INBOX", rig.travel_label} for m in rig.gmail.mail_table.values())


async def test_given_no_item_at_or_above_the_threshold_when_built_then_no_auto_plan_stays_open() -> None:
    rig = Rig()
    rig.request(90)
    rig.gmail.add_mail(("INBOX",), subject="unsure")
    rig.judge.answers = {"unsure": (FINANCE, None, 0.6)}

    await rig.build.run_once()

    plan = rig.store.plan()
    assert rig.store.auto_state[plan.plan_id] is PlanState.REPLACED  # an empty plan is dropped, not approved
    assert _subjects(rig.store.review_items_of(plan)) == {"unsure"}


async def test_given_a_pending_review_plan_when_a_new_request_arrives_then_it_is_replaced_by_a_new_one() -> None:
    rig = await _three_mails(80)
    await rig.build.run_once()
    old = rig.store.plan()
    assert old.state is PlanState.READY  # the review plan is pending, items undecided
    rig.store.auto_state[old.plan_id] = PlanState.APPLIED  # the auto plan finished meanwhile
    rig.request(60)

    await rig.build.run_once()

    plans = rig.store.plans
    assert plans[0].state is PlanState.REPLACED
    assert rig.store.review_items_of(plans[0]) == []  # the old items went with it
    assert len(plans) == 2
    assert plans[1].request_id == rig.store.requests[-1].request_id
    assert plans[1].threshold == 60
