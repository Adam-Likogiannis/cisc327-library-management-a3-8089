import os
import sys
import pytest

# --- Make the repo root importable ---
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import database as db  # the DB access layer
import library_service as ls

# --- Per-test isolated DB ---
@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    temp_db = tmp_path / "unit.db"
    monkeypatch.setattr(db, "DATABASE", str(temp_db), raising=True)
    db.init_database()  # create tables before each test
    yield
    # (no teardown needed; tmp_path is auto-cleaned)

# ----------------- R1: Add Book tests -----------------
# Testing for the function "add_book_to_catalog()"
def test_add_book_invalid_missing_author():
    success, message = ls.add_book_to_catalog("Test Book", "", "0000000000000", 5)
    assert not success
    assert "author is required" in message.lower()

def test_add_book_invalid_negative_copies():
    success, message = ls.add_book_to_catalog("Test Book", "Test Author", "0000000000000", -1)
    assert not success
    assert "positive integer" in message.lower()

def test_add_book_invalid_too_long_isbn():
    # 14 digits -> invalid (must be exactly 13)
    success, message = ls.add_book_to_catalog("Test Book", "Test Author", "12345678901234", 5)
    assert not success
    assert "isbn must be exactly 13" in message.lower()

def test_add_book_duplicate_isbn():
    # First insert should succeed
    ok1, _ = ls.add_book_to_catalog("A", "B", "9990001112223", 1)
    assert ok1
    # Second insert with same ISBN should be rejected
    ok2, msg2 = ls.add_book_to_catalog("C", "D", "9990001112223", 1)
    assert not ok2
    assert "already exists" in msg2.lower()

# ----------------- R3: Borrow Book tests -----------------
# Testing for the function "borrow_book_by_patron()"
def test_borrow_book_valid_input():
    ls.add_book_to_catalog("Test Book", "Test Author", "0000000000000", 5)
    success = ls.borrow_book_by_patron("123456", 1)
    assert success

# ----------------- R4: Return Book tests -----------------
# Testing for the function "return_book_by_patron()"
def test_return_book_by_patron_valid_input():
    ls.add_book_to_catalog("Test Book", "Test Author", "0000000000000", 5)
    ls.borrow_book_by_patron("123456", 1)
    success = ls.return_book_by_patron("123456", 1)
    assert success

# ----------------- R5: Late Fees tests -----------------
# Testing for the function "calculate_late_fee_for_book()"
def test_calculate_late_fee_no_fee():
    ls.add_book_to_catalog("Test Book", "Test Author", "0000000000000", 5)
    ls.borrow_book_by_patron("123456", 1)
    message = ls.calculate_late_fee_for_book("123456", 1)
    assert message == {'days_overdue': 0, 'fee_amount': 0.0, 'status': 'OK'}

# ----------------- R6: Book Search tests -----------------
# Testing for the function "search_books_in_catalog()"
def test_search_books_valid_input():
    ls.add_book_to_catalog("The Great Gatsby", "F. Scott Fitzgerald", "9780743273565", 3)
    ls.add_book_to_catalog("To Kill a Mockingbird", "Harper Lee", "9780061120084", 2)
    ls.add_book_to_catalog("1984", "George Orwell", "9780451524935", 1)
    ls.add_book_to_catalog("Test Book", "Test Author", "0123456789012", 5)
    success = ls.search_books_in_catalog("0123456789012", "isbn")
    assert success

# ----------------- R7: Patron Status tests -----------------
# Testing for the function "get_patron_status_report()"
def test_patron_status_report():
    ls.add_book_to_catalog("The Great Gatsby", "F. Scott Fitzgerald", "9780743273565", 3)
    ls.add_book_to_catalog("To Kill a Mockingbird", "Harper Lee", "9780061120084", 2)
    ls.add_book_to_catalog("1984", "George Orwell", "9780451524935", 1)
    ls.add_book_to_catalog("Test Book", "Test Author", "0123456789012", 5)
    ls.borrow_book_by_patron("123456", 1)
    ls.borrow_book_by_patron("123456", 3)
    ls.borrow_book_by_patron("123456", 4)
    success = ls.get_patron_status_report("123456")
    assert success
