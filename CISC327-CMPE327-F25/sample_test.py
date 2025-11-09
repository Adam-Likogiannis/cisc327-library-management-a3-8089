import os
import sys
import pytest
import importlib

# --- Make the repo root importable ---
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import database as db  # the DB access layer
from services.library_service import add_book_to_catalog

# --- Per-test isolated DB ---
@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    temp_db = tmp_path / "unit.db"
    monkeypatch.setattr(db, "DATABASE", str(temp_db), raising=True)
    db.init_database()  # create tables before each test
    yield
    # (no teardown needed; tmp_path is auto-cleaned)

# ----------------- R1: Add Book tests -----------------

def test_add_book_valid_input():
    success, message = add_book_to_catalog("Test Book", "Test Author", "0000000000000", 5)
    assert success, message
    assert "successfully added" in message.lower()