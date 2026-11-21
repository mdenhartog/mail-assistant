"""U-label-structure-06 (D12): the use case has no trigger of its own; it only continues a plan that exists."""

from __future__ import annotations

import inspect

from app.usecases import resort_build


def test_given_the_build_use_case_then_it_takes_no_debounce_and_has_no_debounce_constant() -> None:
    assert "debounce" not in inspect.signature(resort_build.ResortBuild).parameters
    assert not hasattr(resort_build, "DEBOUNCE")
