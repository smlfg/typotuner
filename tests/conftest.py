"""Shared fixtures for TypoTuner tests."""

import tempfile
from pathlib import Path

import pytest

from typotuner.storage import Storage


@pytest.fixture
def tmp_db(tmp_path):
    """Provide a Storage instance backed by a temporary database."""
    db_path = tmp_path / "test.db"
    storage = Storage(db_path=db_path)
    yield storage
    storage.close()
