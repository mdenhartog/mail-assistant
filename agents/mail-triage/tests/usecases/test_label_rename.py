"""U-label-prefix-removal-06: the rename plan runner (spec AC 4, 5, 18, 20, 26, 27, 29; D8; ADR-0061)."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from app.adapters.gmail_resort import GmailResort, LabelRefused
from app.core.managed import ManagedSet
from app.usecases.label_rename import ItemState, LabelRename, StoredItem
from app.usecases.list_sync import MigrationState
from tests.fakes.fake_gmail import FakeGmail
from tests.fakes.fake_telegram import FakeTelegram
from tests.fakes.rename_store import FakeRenameStore

OLD = "Assistant" + "/"
WRITES = ("labels.create", "labels.patch", "messages.modify")


class SpyGmail(FakeGmail):
    """The Gmail double that also keeps the body of every label patch (colour and visibility must not be in it)."""

    def __init__(self) -> None:
        super().__init__()
        self.patch_bodies: list[dict[str, Any]] = []

    def labels(self) -> Any:
        real = super().labels()
        spy = self

        class _Labels:
            def __getattr__(self, name: str) -> Any:
                return getattr(real, name)

            def patch(self, *, id: str, body: dict[str, Any], **kw: Any) -> Any:  # noqa: A002
                spy.patch_bodies.append(dict(body))
                return real.patch(id=id, body=body, **kw)

        return _Labels()


class World:
    """One mailbox: Gmail, the store, the chat and the runner under test."""

    def __init__(self, state: MigrationState | None = MigrationState.PENDING) -> None:
        self.gmail = SpyGmail()
        self.store = FakeRenameStore(state)
        self.chat = FakeTelegram()
        self.adapter = GmailResort(self.gmail, ManagedSet(()), sleep=lambda _s: None)
        self.runner = LabelRename(self.adapter, self.store, self.chat, page_size=5)

    def old_label(self, name: str, mails: int = 0) -> str:
        label_id = self.gmail.add_label(f"{OLD}{name}")
        for _ in range(mails):
            self.gmail.add_mail(labels=("INBOX", label_id))
        return label_id

    def writes(self) -> list[str]:
        return [call for call in self.gmail.calls if call in WRITES]

    def mails_with(self, label_id: str) -> set[str]:
        return {mid for mid, mail in self.gmail.mail_table.items() if label_id in mail.labels}

    async def planned_and_confirmed(self, skipped: tuple[str, ...] = ()) -> None:
        await self.runner.run_once()
        self.store.confirm(skipped)


def planned(label_id: str, old: str, new: str, state: ItemState = ItemState.PLANNED) -> StoredItem:
    return StoredItem(label_id, old, new, 0, "rename", state)


async def test_given_a_confirmed_label_with_12_mails_when_run_then_it_is_renamed_and_keeps_mail_and_settings() -> None:
    world = World()
    label = world.old_label("Aankopen/Marktplaats", mails=12)
    mails = world.mails_with(label)
    await world.planned_and_confirmed()

    result = await world.runner.run_once()

    assert world.gmail.label_table[label] == "Aankopen/Marktplaats"
    assert world.mails_with(label) == mails
    assert len(mails) == 12
    assert world.gmail.patch_bodies == [{"name": "Aankopen/Marktplaats"}]  # a name only: colour and visibility stay
    assert (result.renamed, world.store.state) == (1, MigrationState.DONE)


async def test_given_old_labels_and_no_confirmation_when_run_then_the_plan_is_built_and_nothing_is_renamed() -> None:
    world = World()
    label = world.old_label("Bills", mails=3)

    first = await world.runner.run_once()
    second = await world.runner.run_once()

    assert world.writes() == []
    assert world.gmail.label_table[label] == f"{OLD}Bills"
    assert (first.built, second.built) == (1, 0)  # built once
    assert world.store.stored[label].mail_count == 3
    assert (world.store.state, world.chat.texts) == (MigrationState.PENDING, [])


async def test_given_a_confirmed_state_without_a_confirmation_row_when_run_then_nothing_is_renamed() -> None:
    world = World(MigrationState.CONFIRMED)
    label = world.old_label("Bills", mails=1)
    world.store.stored[label] = planned(label, f"{OLD}Bills", "Bills")

    await world.runner.run_once()

    assert world.writes() == []
    assert world.store.state is MigrationState.CONFIRMED


async def test_given_a_mailbox_without_a_rename_state_when_run_then_nothing_happens() -> None:
    world = World(None)
    world.old_label("Bills")

    await world.runner.run_once()

    assert world.gmail.calls == []


async def test_given_no_old_labels_when_the_plan_is_built_then_the_state_is_done_at_once() -> None:
    world = World()
    world.gmail.add_label("Bills")

    await world.runner.run_once()

    assert world.store.state is MigrationState.DONE
    assert world.writes() == []


async def test_given_an_old_and_an_existing_label_when_run_then_mail_is_merged_and_a_rerun_changes_nothing() -> None:
    world = World()
    old = world.old_label("Amerika", mails=12)  # 12 mails, pages of 5
    existing = world.gmail.add_label("Amerika")
    mixed = world.gmail.add_mail(labels=("INBOX", old, existing))  # already on both
    elsewhere = world.gmail.add_mail(labels=("INBOX", existing))
    moved = world.mails_with(old)
    await world.planned_and_confirmed()
    assert world.store.stored[old].action == "merge"

    await world.runner.run_once()
    after = {mid: set(mail.labels) for mid, mail in world.gmail.mail_table.items()}
    calls = len(world.gmail.calls)
    await world.runner.run_once()

    assert world.mails_with(existing) == moved | {elsewhere}
    assert mixed in world.mails_with(existing)
    assert world.mails_with(old) == set()
    assert world.gmail.label_table[old] == f"{OLD}Amerika"  # the label itself is neither renamed nor deleted here
    assert {mid: set(mail.labels) for mid, mail in world.gmail.mail_table.items()} == after
    assert [c for c in world.gmail.calls[calls:] if c in WRITES] == []
    assert world.store.state is MigrationState.DONE


async def test_given_a_crash_in_the_middle_of_a_merge_when_rerun_then_no_mail_is_lost() -> None:
    world = World()
    old = world.old_label("Amerika", mails=3)
    existing = world.gmail.add_label("Amerika")
    mails = world.mails_with(old)
    await world.planned_and_confirmed()
    world.gmail.fail_after_next_change()  # the first add is made, its answer is lost

    with pytest.raises(ConnectionResetError):
        await world.runner.run_once()
    await world.runner.run_once()

    assert world.mails_with(existing) == mails
    assert world.mails_with(old) == set()


async def test_given_a_label_renamed_by_hand_after_the_preview_when_run_then_it_is_skipped_and_reported() -> None:
    world = World()
    changed = world.old_label("Bills", mails=2)
    other = world.old_label("Work", mails=1)
    await world.planned_and_confirmed()
    world.gmail.label_table[changed] = "My own name"  # the user, between the preview and the run

    result = await world.runner.run_once()

    assert world.gmail.label_table[changed] == "My own name"
    assert world.gmail.label_table[other] == "Work"
    assert world.store.states() == {changed: ItemState.KEPT, other: ItemState.DONE}
    assert (result.kept, result.renamed) == (1, 1)
    assert "1 left as they were" in world.chat.texts[0]


async def test_given_a_label_deleted_by_hand_after_the_preview_when_run_then_it_is_kept_and_the_rest_goes_on() -> None:
    world = World()
    gone = world.old_label("Gone")
    other = world.old_label("Work")
    await world.planned_and_confirmed()
    world.gmail.delete_label(gone)

    await world.runner.run_once()

    assert world.store.states() == {gone: ItemState.KEPT, other: ItemState.DONE}
    assert world.store.state is MigrationState.DONE


async def test_given_a_name_taken_after_the_preview_when_run_then_the_rename_is_kept_not_forced() -> None:
    world = World()
    label = world.old_label("Bills", mails=1)
    await world.planned_and_confirmed()
    world.gmail.add_label("Bills")  # a rename now would clash: the plan is not what the user saw

    await world.runner.run_once()

    assert world.gmail.label_table[label] == f"{OLD}Bills"
    assert world.store.states() == {label: ItemState.KEPT}


async def test_given_an_item_the_user_skipped_when_run_then_it_is_not_touched() -> None:
    world = World()
    skipped = world.old_label("Keep me", mails=2)
    other = world.old_label("Work", mails=1)
    await world.planned_and_confirmed(skipped=(skipped,))

    await world.runner.run_once()

    assert world.gmail.label_table[skipped] == f"{OLD}Keep me"
    assert world.store.states() == {skipped: ItemState.SKIPPED, other: ItemState.DONE}
    assert "1 skipped by you" in world.chat.texts[0]
    assert world.gmail.patch_bodies == [{"name": "Work"}]


async def test_given_a_crash_after_3_of_10_items_when_restarted_then_it_continues_and_done_comes_at_the_end() -> None:
    world = World()
    ids = [world.old_label(f"Label {n:02d}", mails=1) for n in range(10)]
    await world.planned_and_confirmed()
    world.store.crash_after_settles = 3

    with pytest.raises(ConnectionResetError):
        await world.runner.run_once()
    assert sum(state is ItemState.DONE for state in world.store.states().values()) == 3
    assert world.store.state is MigrationState.CONFIRMED  # not done: seven items wait
    assert world.chat.texts == []
    world.gmail.patch_bodies.clear()
    await world.runner.run_once()

    assert all(state is ItemState.DONE for state in world.store.states().values())
    assert len(world.gmail.patch_bodies) == 6  # the item that crashed was renamed already: it is settled, not redone
    assert world.store.state is MigrationState.DONE
    assert [world.gmail.label_table[i] for i in ids] == [f"Label {n:02d}" for n in range(10)]
    assert len(world.chat.texts) == 1


async def test_given_a_completed_rename_when_restored_then_old_names_return_and_mail_is_intact() -> None:
    world = World()
    label = world.old_label("Aankopen/Marktplaats", mails=4)
    mails = world.mails_with(label)
    await world.planned_and_confirmed()
    await world.runner.run_once()
    world.chat.texts.clear()
    world.store.request_restore()

    result = await world.runner.run_once()

    assert world.gmail.label_table[label] == f"{OLD}Aankopen/Marktplaats"
    assert world.mails_with(label) == mails
    assert (result.restored, world.store.restore_open, world.store.restores_closed) == (1, None, 1)
    assert len(world.chat.texts) == 1
    assert world.store.state is MigrationState.DONE


async def test_given_a_restore_when_a_label_changed_since_then_it_is_left_alone() -> None:
    world = World()
    label = world.old_label("Bills", mails=1)
    await world.planned_and_confirmed()
    await world.runner.run_once()
    world.gmail.label_table[label] = "Renamed again by hand"
    world.store.request_restore()

    result = await world.runner.run_once()

    assert world.gmail.label_table[label] == "Renamed again by hand"
    assert (result.restored, result.kept) == (0, 1)


async def test_given_a_merge_when_restore_is_requested_then_the_mail_stays_where_it_is_and_it_is_counted() -> None:
    world = World()
    old = world.old_label("Amerika", mails=2)
    existing = world.gmail.add_label("Amerika")
    mails = world.mails_with(old)
    await world.planned_and_confirmed()
    await world.runner.run_once()
    world.chat.texts.clear()
    world.store.request_restore()

    await world.runner.run_once()

    assert world.mails_with(existing) == mails  # which mail was moved is not recorded: the limit is documented
    assert world.mails_with(old) == set()
    assert "1 merges stay" in world.chat.texts[0]


async def test_given_a_restore_during_the_run_when_run_then_waiting_items_are_not_renamed_after() -> None:
    world = World()
    first = world.old_label("Aaa", mails=1)
    second = world.old_label("Bbb", mails=1)
    await world.planned_and_confirmed()
    world.store.stored[first] = planned(first, f"{OLD}Aaa", "Aaa", ItemState.DONE)
    world.gmail.label_table[first] = "Aaa"
    world.store.request_restore()

    await world.runner.run_once()

    assert world.gmail.label_table[first] == f"{OLD}Aaa"
    assert world.gmail.label_table[second] == f"{OLD}Bbb"
    assert world.store.state is MigrationState.DONE


async def test_given_a_merge_into_the_archive_label_when_run_then_it_is_kept_and_no_mail_gets_it() -> None:
    world = World()
    old = world.old_label("Archive", mails=2)
    archive = world.gmail.add_label("Archive")
    await world.planned_and_confirmed()

    await world.runner.run_once()

    assert world.store.states() == {old: ItemState.KEPT}
    assert world.mails_with(archive) == set()


async def test_given_a_merge_into_labels_with_stored_archive_and_other_ids_when_run_then_they_are_kept_by_id() -> None:
    """RED-003: renamed by hand, so the names are no longer the settings; the stored ids still are."""
    world = World()
    old_archive, old_other = world.old_label("Misc", mails=2), world.old_label("Rest", mails=1)
    archive, other = world.gmail.add_label("Misc"), world.gmail.add_label("Rest")
    world.store.protected = frozenset({archive, other})
    await world.planned_and_confirmed()

    await world.runner.run_once()

    assert world.store.states() == {old_archive: ItemState.KEPT, old_other: ItemState.KEPT}
    assert world.mails_with(archive) == world.mails_with(other) == set()


async def test_given_a_rename_run_when_the_guard_is_asked_then_it_knows_only_the_label_of_the_item_in_hand() -> None:
    world = World()
    label = world.old_label("Bills")
    user_label = world.gmail.add_label("Private")
    await world.planned_and_confirmed()
    original = world.adapter.rename_label
    refusals: list[str] = []

    def spy(label_id: str, new_name: str) -> Any:
        try:
            original(user_label, "Hijacked")  # a label that is not the item in hand
        except LabelRefused as error:
            refusals.append(str(error))
        return original(label_id, new_name)

    world.adapter.rename_label = spy  # type: ignore[method-assign]

    await world.runner.run_once()

    assert refusals == ["label_not_managed"]
    assert world.gmail.label_table[user_label] == "Private"
    with pytest.raises(LabelRefused):
        original(label, "Anything")  # nothing stays allowed after the run


async def test_given_the_notice_and_the_logs_when_written_then_they_carry_counts_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    world = World()
    world.old_label("Zebra-Secret-Project", mails=2)
    refused = world.old_label("Refused-Name")
    world.gmail.refuse_name("Refused-Name")  # Gmail refuses the new name: the item is kept
    caplog.set_level(logging.DEBUG)
    await world.planned_and_confirmed()

    await world.runner.run_once()
    world.store.request_restore()
    await world.runner.run_once()

    text = " ".join([*world.chat.texts, *(record.getMessage() for record in caplog.records)])
    assert "Zebra" not in text
    assert "Refused" not in text
    assert len(world.chat.texts) == 2  # one when the rename is done, one when the restore is done
    assert world.store.states()[refused] is ItemState.KEPT
