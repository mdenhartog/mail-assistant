"""U-mail-categories-16: the plan buttons reach their handler and never touch the conversation (AC-48)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.test_dispatch import Rig, button

if TYPE_CHECKING:
    from app.adapters.telegram_inbox import Command


class _Actions:
    def __init__(self) -> None:
        self.seen: list[tuple[str, str]] = []

    async def on_button(self, command: Command, action: str, nonce: str) -> None:
        self.seen.append((action, nonce))


async def test_given_the_plan_buttons_when_pressed_then_they_reach_the_plan_actions_with_action_and_nonce() -> None:
    rig = Rig()
    actions = _Actions()
    router = rig.router()
    router.register_plan_actions(actions)  # type: ignore[arg-type]
    nonce = "A" * 22

    for name in ("plancancel", "planlock", "planback"):
        await router.handle(button(f"{name}:{nonce}"))

    assert actions.seen == [("plancancel", nonce), ("planlock", nonce), ("planback", nonce)]
    assert rig.chat.acknowledged == ["cb1"] * 3


async def test_given_no_plan_actions_or_a_malformed_button_when_pressed_then_nothing_happens() -> None:
    rig = Rig()
    actions = _Actions()
    await rig.router().handle(button(f"plancancel:{'A' * 22}"))  # not registered
    router = rig.router()
    router.register_plan_actions(actions)  # type: ignore[arg-type]
    await router.handle(button("plancancel:short"))

    assert actions.seen == []
    assert rig.chat.edited == []
    assert rig.chat.said == []
