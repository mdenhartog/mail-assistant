"""U-quiet-hours-10 on a real PostgreSQL: the zone dialogue with the real settings store and conversation row."""

from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING

from sqlalchemy import text

from schedule_policy.testing import make_policy
from tests.db.test_settings_dialog_pg import engine, rig  # noqa: F401  # the fixtures of the U-09 database tests
from tests.usecases.test_dispatch import text as _typed

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

    from tests.db.test_settings_dialog_pg import Rig


async def _audit_count(pg: AsyncEngine) -> int:
    async with pg.connect() as connection:
        return (await connection.execute(text("select count(*) from settings.settings_change"))).scalar_one()


async def test_given_a_city_when_answered_then_the_zone_is_stored_with_one_audit_record(
    rig: Rig,  # noqa: F811
    engine: AsyncEngine,  # noqa: F811
) -> None:
    await rig.store.write(make_policy(overview_at=time(17, 0)), 0, "web", "seed")
    await rig.router.handle(_typed("/settings"))
    await rig.press("Change time zone")

    await rig.say("New York")

    stored = await rig.store.read()
    assert stored is not None
    assert (stored.version, stored.updated_via) == (2, "telegram")
    assert stored.policy == make_policy(overview_at=time(17, 0), zone="America/New_York")
    assert await _audit_count(engine) == 2  # the seed and ONE change


async def test_given_candidate_buttons_when_one_is_tapped_then_the_chosen_zone_is_stored(
    rig: Rig,  # noqa: F811
) -> None:
    await rig.router.handle(_typed("/settings"))
    await rig.press("Change time zone")
    await rig.say("Paris")
    assert await rig.store.read() is None  # the choices alone store nothing

    await rig.press("Paris, France (UTC+1)")

    stored = await rig.store.read()
    assert stored is not None
    assert (stored.version, stored.policy.zone) == (1, "Europe/Paris")


async def test_given_another_writer_between_question_and_answer_when_answered_then_the_other_value_survives(
    rig: Rig,  # noqa: F811
) -> None:
    await rig.store.write(make_policy(), 0, "web", "seed")
    await rig.router.handle(_typed("/settings"))
    await rig.press("Change time zone")
    await rig.store.write(make_policy(remind_at=time(8, 0)), 1, "web", "other")

    await rig.say("Tokyo")

    stored = await rig.store.read()
    assert stored is not None
    assert (stored.version, stored.policy.remind_at, stored.policy.zone) == (2, time(8, 0), "Europe/Amsterdam")
    assert rig.chat.sent[-1].text.splitlines()[0].startswith("Your settings changed elsewhere.")


async def test_given_another_writer_between_choices_and_tap_when_tapped_then_the_other_value_survives(
    rig: Rig,  # noqa: F811
) -> None:
    await rig.store.write(make_policy(), 0, "web", "seed")
    await rig.router.handle(_typed("/settings"))
    await rig.press("Change time zone")
    await rig.say("Paris")
    await rig.store.write(make_policy(remind_at=time(8, 0)), 1, "web", "other")

    await rig.press("Paris, France (UTC+1)")

    stored = await rig.store.read()
    assert stored is not None
    assert (stored.version, stored.policy.remind_at, stored.policy.zone) == (2, time(8, 0), "Europe/Amsterdam")
    assert rig.chat.sent[-1].text.startswith("Your settings changed elsewhere.")


async def test_given_the_conversation_row_when_choices_are_shown_then_it_keeps_indexes_into_zones_not_in_buttons(
    rig: Rig,  # noqa: F811
    engine: AsyncEngine,  # noqa: F811
) -> None:
    await rig.router.handle(_typed("/settings"))
    await rig.press("Change time zone")
    await rig.say("Paris")

    data = [b.data for b in rig.chat.sent[-1].buttons]

    assert all(not part.startswith(("Europe", "America")) for datum in data for part in datum.split(":"))
    async with engine.connect() as connection:
        partial = (await connection.execute(text("select partial::text from conversation"))).scalar_one()
    assert "Europe/Paris" in partial  # the candidates live in the row, behind the index
