import pytest

from app.settings import Settings
from tests import DEV


@pytest.fixture
def settings() -> Settings:
    return Settings.from_env(DEV)
