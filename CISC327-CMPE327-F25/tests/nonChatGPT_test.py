import os
import sys
from datetime import datetime, timedelta
import importlib
import pytest

# --- Make the repo root importable ---
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import database as db
import library_service as ls

# ---------- Shared fixtures ----------
@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    temp_db = tmp_path / "unit.db"
    monkeypatch.setattr(db, "DATABASE", str(temp_db), raising=True)
    db.init_database()
    yield

def _add(title, author, isbn, total=1):
    ok, msg = ls.add_book_to_catalog(title, author, isbn, total)
    assert ok, msg
    return db.get_book_by_isbn(isbn)

def _borrow_exact_overdue(book_id: int, patron: str, days_overdue: int):
    """Create an active borrow with due_date = today - days_overdue."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    due_dt = today - timedelta(days=days_overdue)
    borrow_dt = due_dt - timedelta(days=14)
    assert db.insert_borrow_record(patron, book_id, borrow_dt, due_dt)
    assert db.update_book_availability(book_id, -1)

# =========================================================
# R1 — add_book_to_catalog
# =========================================================
def test_r1_add_book_valid_input():
    success, message = ls.add_book_to_catalog("Test Book", "Test Author", "0123456789012", 5)
    assert success, message
    assert "successfully added" in message.lower()

def test_r1_missing_author():
    success, message = ls.add_book_to_catalog("Test Book", "", "1234567890123", 5)
    assert not success
    assert "author is required" in message.lower()

def test_r1_bad_isbn_length():
    success, message = ls.add_book_to_catalog("Test Book", "Test Author", "12345678901234", 5)
    assert not success
    assert "isbn must be exactly 13" in message.lower()

def test_r1_non_positive_total_copies():
    success, message = ls.add_book_to_catalog("Test Book", "Test Author", "1234567890123", 0)
    assert not success
    assert "positive integer" in message.lower()

def test_r1_duplicate_isbn_rejected():
    ok1, msg1 = ls.add_book_to_catalog("A", "B", "9990001112223", 1)
    assert ok1, msg1
    ok2, msg2 = ls.add_book_to_catalog("C", "D", "9990001112223", 1)
    assert not ok2
    assert "already exists" in msg2.lower()


# =========================================================
# R3 — borrow_book_by_patron
# =========================================================
def test_r3_borrow_success_happy_path():
    book = _add("Borrowable", "Auth", "1111111111111", 2)
    success, message = ls.borrow_book_by_patron("123456", book["id"])
    assert success, message
    assert "due date" in message.lower()

def test_r3_invalid_patron_id():
    book = _add("Book", "Auth", "2222222222222", 1)
    success, message = ls.borrow_book_by_patron("12A456", book["id"])
    assert not success
    assert "invalid patron id" in message.lower()

def test_r3_book_not_found():
    success, message = ls.borrow_book_by_patron("123456", 99999)
    assert not success
    assert "book not found" in message.lower()

def test_r3_unavailable_when_no_copies_left():
    # 1 copy → first borrow ok, second rejected
    book = _add("Single Copy", "Auth", "3333333333333", 1)
    ok1, msg1 = ls.borrow_book_by_patron("123456", book["id"])
    assert ok1, msg1
    ok2, msg2 = ls.borrow_book_by_patron("654321", book["id"])
    assert not ok2
    assert "not available" in msg2.lower()

# =========================================================
# R4 — return_book_by_patron
# =========================================================
def test_r4_return_success_increments_availability():
    book = _add("Return Me", "Auth", "5555555555555", 2)
    before = db.get_book_by_id(book["id"])["available_copies"]
    ok_b, msg_b = ls.borrow_book_by_patron("123456", book["id"])
    assert ok_b, msg_b
    ok_r, msg_r = ls.return_book_by_patron("123456", book["id"])
    assert ok_r, msg_r
    after = db.get_book_by_id(book["id"])["available_copies"]
    assert after == before

def test_r4_return_book_not_found():
    ok, msg = ls.return_book_by_patron("123456", 99999)
    assert not ok
    assert "book not found" in msg.lower()

def test_r4_return_wrong_patron_fails():
    book = _add("Owned by A", "Auth", "6666666666666", 1)
    ok_b, msg_b = ls.borrow_book_by_patron("111111", book["id"])
    assert ok_b, msg_b
    ok_r, msg_r = ls.return_book_by_patron("222222", book["id"])
    assert not ok_r
    assert "not currently being borrowed by this patron" in msg_r.lower()

def test_r4_double_return_second_fails():
    book = _add("Return Once", "Auth", "7777777777777", 1)
    ok_b, msg_b = ls.borrow_book_by_patron("123456", book["id"])
    assert ok_b, msg_b
    ok1, msg1 = ls.return_book_by_patron("123456", book["id"])
    assert ok1, msg1
    ok2, msg2 = ls.return_book_by_patron("123456", book["id"])
    assert not ok2
    assert "not currently being borrowed" in msg2.lower()


# =========================================================
# R5 — calculate_late_fee_for_book
# =========================================================
def test_r5_invalid_patron_id():
    book = _add("Fee Book", "Auth", "8888888888888", 1)
    result = ls.calculate_late_fee_for_book("12A456", book["id"])
    assert result["status"].lower().startswith("invalid patron")
    assert result["fee_amount"] == 0.0 and result["days_overdue"] == 0

def test_r5_book_not_found():
    result = ls.calculate_late_fee_for_book("123456", 99999)
    assert result["status"].lower().startswith("book not found")

def test_r5_not_currently_borrowed():
    book = _add("Idle", "Auth", "9999999999999", 1)
    result = ls.calculate_late_fee_for_book("123456", book["id"])
    assert result["status"].lower().startswith("book not currently borrowed")

@pytest.mark.parametrize("days,expected", [
    (0, 0.00),
    (3, 1.50),   # 3 * 0.50
    (7, 3.50),   # 7 * 0.50
    (8, 4.50),   # 3.50 + 1
    (20, 15.00), # capped at 15.00
])
def test_r5_fee_schedule(days, expected):
    book = _add(f"Fee{days}", "Auth", f"1234567890{days:03d}"[-13:], 1)
    _borrow_exact_overdue(book["id"], "555555", days)
    result = ls.calculate_late_fee_for_book("555555", book["id"])
    assert result["status"] == "OK"
    assert result["days_overdue"] == days
    assert abs(result["fee_amount"] - expected) < 1e-6, result


# =========================================================
# R6 — search_books_in_catalog
# =========================================================
def test_r6_empty_or_blank_returns_empty():
    assert ls.search_books_in_catalog("", "title") == []
    assert ls.search_books_in_catalog("   ", "author") == []

def test_r6_title_partial_casefold():
    _add("The Great Gatsby", "F. Scott Fitzgerald", "0743273565000", 3)
    res = ls.search_books_in_catalog("great", "title")
    assert any("great gatsby" in b["title"].lower() for b in res)

def test_r6_author_partial_casefold():
    _add("To Kill a Mockingbird", "Harper Lee", "0061120084000", 2)
    res = ls.search_books_in_catalog("harper", "author")
    assert any("harper lee" in f'{b["author"]}'.lower() for b in res)

def test_r6_isbn_exact_ignoring_dashes():
    _add("1984", "George Orwell", "0451524935000", 1)
    res = ls.search_books_in_catalog("0451-524-935-000", "isbn")
    assert len(res) == 1 and res[0]["isbn"] == "0451524935000"

def test_r6_unknown_type_behaves_like_all():
    _add("Brave New World", "Aldous Huxley", "1231231231231", 2)
    res = ls.search_books_in_catalog("huxley", "something_else")
    assert any("huxley" in f'{b["author"]}'.lower() for b in res)


# =========================================================
# R7 — get_patron_status_report
# =========================================================
def test_r7_invalid_patron_id():
    report = ls.get_patron_status_report("abc123")
    assert report["status"].lower().startswith("invalid patron")
    assert report["borrowed_count"] == 0
    assert report["remaining_allowance"] == 5

def test_r7_no_loans_ok_summary():
    report = ls.get_patron_status_report("222222")
    assert report["status"] == "OK"
    assert report["borrowed_count"] == 0
    assert report["remaining_allowance"] == 5
    assert report["overdue_count"] == 0
    assert report["next_due_date"] is None
    assert report["borrowed_books"] == []

def test_r7_counts_overdue_and_next_due():
    # two loans: one overdue by 2 days, one due in 3 days
    bA = _add("A", "Auth", "3213213213213", 3)
    bB = _add("B", "Auth", "6546546546546", 3)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # overdue by 2
    due_A = today - timedelta(days=2)
    borrow_A = due_A - timedelta(days=14)
    assert db.insert_borrow_record("123456", bA["id"], borrow_A, due_A)
    assert db.update_book_availability(bA["id"], -1)

    # due in 3
    due_B = today + timedelta(days=3)
    borrow_B = due_B - timedelta(days=14)
    assert db.insert_borrow_record("123456", bB["id"], borrow_B, due_B)
    assert db.update_book_availability(bB["id"], -1)

    report = ls.get_patron_status_report("123456")
    assert report["status"] == "OK"
    assert report["borrowed_count"] == 2
    assert report["remaining_allowance"] == 3
    assert report["overdue_count"] == 1
    assert report["next_due_date"] == min(due_A, due_B).isoformat()
    assert len(report["borrowed_books"]) == 2

def test_r7_borrowed_books_entries_have_required_fields():
    b = _add("Entry Fields", "Auth", "7778889990001", 1)
    ok, msg = ls.borrow_book_by_patron("999999", b["id"])
    assert ok, msg
    rep = ls.get_patron_status_report("999999")
    assert isinstance(rep.get("borrowed_books"), list)
    for entry in rep["borrowed_books"]:
        for key in ("book_id", "title", "borrow_date", "due_date", "days_overdue"):
            assert key in entry

def test_r7_remaining_allowance_drops_as_you_borrow():
    b1 = _add("bk1", "a", "8600000000001", 1)
    b2 = _add("bk2", "a", "8600000000002", 1)
    ls.borrow_book_by_patron("121212", b1["id"])
    rep1 = ls.get_patron_status_report("121212")
    assert rep1["borrowed_count"] == 1 and rep1["remaining_allowance"] == 4
    ls.borrow_book_by_patron("121212", b2["id"])
    rep2 = ls.get_patron_status_report("121212")
    assert rep2["borrowed_count"] == 2 and rep2["remaining_allowance"] == 3
