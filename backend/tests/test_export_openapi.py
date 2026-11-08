import json
from pathlib import Path

from app.export_openapi import build_document, main


def test_given_the_app_when_building_the_document_then_it_is_openapi_with_the_health_routes() -> None:
    document = json.loads(build_document())

    assert document["openapi"].startswith("3.")
    assert "/healthz" in document["paths"]


def test_given_the_app_when_building_twice_then_the_output_is_identical_and_ends_with_a_newline() -> None:
    assert build_document() == build_document()
    assert build_document().endswith("\n")


def test_given_no_file_when_writing_then_the_document_is_created(tmp_path: Path) -> None:
    target = tmp_path / "docs" / "api" / "openapi.json"

    assert main([str(target)]) == 0

    assert target.read_text(encoding="utf-8") == build_document()


def test_given_a_current_file_when_checking_then_exit_code_is_zero(tmp_path: Path) -> None:
    target = tmp_path / "openapi.json"
    target.write_text(build_document(), encoding="utf-8")

    assert main([str(target), "--check"]) == 0


def test_given_a_stale_or_missing_file_when_checking_then_exit_code_is_one_and_nothing_written(tmp_path: Path) -> None:
    stale = tmp_path / "stale.json"
    stale.write_text("{}\n", encoding="utf-8")
    missing = tmp_path / "missing.json"

    assert main([str(stale), "--check"]) == 1
    assert main([str(missing), "--check"]) == 1
    assert stale.read_text(encoding="utf-8") == "{}\n"
    assert not missing.exists()
