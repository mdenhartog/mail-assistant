"""REV-006: the debounce time has one source, the setting; the use case has no default of its own."""

from __future__ import annotations

import inspect

from app.usecases import resort_build


def test_given_the_build_use_case_then_the_debounce_has_no_default_value() -> None:
    parameter = inspect.signature(resort_build.ResortBuild).parameters["debounce"]

    assert parameter.default is inspect.Parameter.empty
    assert not hasattr(resort_build, "DEBOUNCE")
