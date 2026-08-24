"""
conftest.py — shared pytest fixtures for all test modules.

The `tmp_db` fixture patches storage.DB_PATH to point at a temporary file
for each test, then tears it down automatically. This means every test that
uses storage gets a fresh, empty database — no test can pollute another.
"""

import pytest
import storage


@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    """Redirect storage to a fresh temp SQLite file for the duration of the test."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(storage, "DB_PATH", db_file)
    storage.init_db()
    yield db_file
    # tmp_path is cleaned up automatically by pytest after the test
