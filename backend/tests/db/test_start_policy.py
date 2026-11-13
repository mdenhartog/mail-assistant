"""U-web-settings-62, criterion 1 (CR-02): a failed container start fails the run in CI; only no Docker skips."""

import pytest
from docker.errors import APIError, DockerException, ImageNotFound
from requests.exceptions import ConnectionError as RequestsConnectionError

from tests.db.conftest import report_start_failure, start_failure_outcome

NO_DOCKER = [
    DockerException("Error while fetching server API version"),
    RequestsConnectionError("Connection aborted"),
    FileNotFoundError("docker.sock"),
    ConnectionRefusedError("refused"),
]
REAL_FAULTS = [
    ImageNotFound("no such image"),
    APIError("server error"),
    RuntimeError("container exited"),
    TimeoutError("readiness"),
]


@pytest.mark.parametrize("error", NO_DOCKER + REAL_FAULTS, ids=lambda error: type(error).__name__)
def test_given_ci_is_set_when_the_container_fails_to_start_then_the_run_fails(error: Exception) -> None:
    assert start_failure_outcome(error, ci=True) == "fail"


@pytest.mark.parametrize("error", NO_DOCKER, ids=lambda error: type(error).__name__)
def test_given_no_ci_when_docker_is_unavailable_then_the_tests_skip(error: Exception) -> None:
    assert start_failure_outcome(error, ci=False) == "skip"


@pytest.mark.parametrize("error", REAL_FAULTS, ids=lambda error: type(error).__name__)
def test_given_no_ci_when_the_container_fails_for_another_reason_then_the_run_fails(error: Exception) -> None:
    assert start_failure_outcome(error, ci=False) == "fail"


def test_given_ci_is_set_in_the_environment_when_a_start_failure_is_reported_then_it_raises_a_failure() -> None:
    with pytest.raises(pytest.fail.Exception):
        report_start_failure(DockerException("no docker"), "postgres:16", {"CI": "true"})


def test_given_ci_is_unset_when_docker_is_missing_then_a_start_failure_is_reported_as_a_skip() -> None:
    with pytest.raises(pytest.skip.Exception):
        report_start_failure(DockerException("no docker"), "postgres:16", {})


def test_given_an_empty_ci_variable_when_docker_is_missing_then_it_counts_as_unset() -> None:
    with pytest.raises(pytest.skip.Exception):
        report_start_failure(DockerException("no docker"), "postgres:16", {"CI": ""})
