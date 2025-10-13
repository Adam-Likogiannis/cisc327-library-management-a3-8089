import os, sys, importlib, importlib.util
from datetime import datetime, timedelta
import pytest

# ---- Make repo root importable ------------------------------------------------
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# ---- Import the database layer (functions that talk to library.db) ------------
try:
    import database as db
except ModuleNotFoundError:
    db_path = os.path.join(REPO_ROOT, "database.py")
    spec = importlib.util.spec_from_file_location("database", db_path)
    db = importlib.module_from_spec(spec)
    sys.modules["database"] = db
    spec.loader.exec_module(db)

def _reload_library_service():
    """Reload after db.DATABASE is patched so the service binds to the temp DB."""
    if "library_service" in importlib.sys.modules:
        del importlib.sys.modules["library_service"]
    import library_service
    return importlib.reload(library_service)

# ---- Per-test isolated SQLite file -------------------------------------------
@pytest.fixture(scope="session")
def temp_db_path(tmp_path_factory):
    return tmp_path_factory.mktemp("libdb") / "test_library.db"

@pytest.fixture(autouse=True)
def isolated_db(temp_db_path, monkeypatch):
    # Point database.py at a temp file (NOT your real library.db)
    monkeypatch.setattr(db, "DATABASE", str(temp_db_path), raising=True)

    # Create schema and add the sample seed from your db module
    db.init_database()
    db.add_sample_data()  # Gatsby / Mockingbird / 1984; 1984 pre-borrowed

    yield

    # Tear down the temp DB file
    try:
        os.remove(str(temp_db_path))
    except FileNotFoundError:
        pass


###############################################################################
# R1: add_book_to_catalog tests (validation + happy path)  :contentReference[oaicite:8]{index=8}
###############################################################################

@pytest.mark.parametrize(
    "title,author,isbn,total,expected_msg_substr",
    [
        ("", "Author", "1234567890123", 1, "Title is required"),
        ("A"*201, "Author", "1234567890123", 1, "less than 200"),
        ("Title", "", "1234567890123", 1, "Author is required"),
        ("Title", "A"*101, "1234567890123", 1, "less than 100"),
        ("Title", "Author", "123", 1, "ISBN must be exactly 13"),
        ("Title", "Author", "1234567890123", 0, "positive integer"),
    ],
)
def test_r1_add_book_validation_errors(isolated_db, title, author, isbn, total, expected_msg_substr):
    ls = _reload_library_service()
    ok, msg = ls.add_book_to_catalog(title, author, isbn, total)
    assert not ok
    assert expected_msg_substr in msg

def test_r1_add_book_duplicate_isbn(isolated_db):
    ls = _reload_library_service()
    # Use an existing ISBN from seed
    ok, msg = ls.add_book_to_catalog("New Title", "New Author", "9780743273565", 1)
    assert not ok
    assert "already exists" in msg  # duplicate ISBN must be rejected  :contentReference[oaicite:9]{index=9}

def test_r1_add_book_success(isolated_db):
    ls = _reload_library_service()
    ok, msg = ls.add_book_to_catalog("Clean Code", "Robert C. Martin", "9780132350884", 2)
    assert ok
    assert 'has been successfully added' in msg
    # Ensure it actually exists
    book = db.get_book_by_isbn("9780132350884")
    assert book and book["total_copies"] == 2 and book["available_copies"] == 2

###############################################################################
# R3: borrow_book_by_patron tests  :contentReference[oaicite:10]{index=10}
###############################################################################

def test_r3_borrow_invalid_patron_id(isolated_db):
    ls = _reload_library_service()
    ok, msg = ls.borrow_book_by_patron("12A456", 1)
    assert not ok and "Invalid patron ID" in msg

def test_r3_borrow_book_not_found(isolated_db):
    ls = _reload_library_service()
    ok, msg = ls.borrow_book_by_patron("123456", 9999)
    assert not ok and "Book not found" in msg

def test_r3_borrow_when_unavailable(isolated_db):
    ls = _reload_library_service()

    # Create a single-copy book that is AVAILABLE
    assert db.insert_book("Single Copy", "Author", "1234567890999", 1, 1)
    b = db.get_book_by_isbn("1234567890999")

    # First borrow should succeed
    ok1, msg1 = ls.borrow_book_by_patron("123456", b["id"])
    assert ok1, f"first borrow failed: {msg1}"

    # Second borrow should fail because no copies remain
    ok2, msg2 = ls.borrow_book_by_patron("654321", b["id"])
    assert not ok2 and "not available" in msg2.lower()

def test_r3_borrow_limit_boundary_at_five(isolated_db):
    """
    Requirement: max 5 books may be borrowed (the 6th should be rejected).  :contentReference[oaicite:11]{index=11}
    """
    ls = _reload_library_service()
    patron = "123456"

    # Insert extra books so we can borrow several distinct titles
    for i in range(10):
        assert db.insert_book(f"Book{i}", "Author", f"99999999999{i%10}", 1, 1)

    # Borrow 5 different books
    borrowed_ids = []
    all_books = db.get_all_books()
    for b in all_books:
        if b["available_copies"] > 0 and b["id"] not in (1, 2, 3):  # avoid seed overlap
            ok, _ = ls.borrow_book_by_patron(patron, b["id"])
            if ok:
                borrowed_ids.append(b["id"])
            if len(borrowed_ids) == 5:
                break
    assert len(borrowed_ids) == 5

    # Attempt the 6th borrow — must be rejected (R3).
    # NOTE: Current code checks `> 5` instead of `>= 5`, so this will fail in your implementation.
    next_book = next(b for b in db.get_all_books() if b["available_copies"] > 0 and b["id"] not in borrowed_ids)
    ok6, msg6 = ls.borrow_book_by_patron(patron, next_book["id"])
    assert not ok6, "Borrowing the 6th book should be rejected per R3 (max 5)."
    assert "maximum borrowing limit of 5" in msg6  # :contentReference[oaicite:12]{index=12}

###############################################################################
# R4: return_book_by_patron tests  :contentReference[oaicite:13]{index=13}
###############################################################################

def test_r4_return_nonexistent_book(isolated_db):
    ls = _reload_library_service()
    ok, msg = ls.return_book_by_patron("123456", 9999)
    assert not ok and "Book not found" in msg

def test_r4_return_not_borrowed_by_patron(isolated_db):
    ls = _reload_library_service()
    # Patron A borrows
    ok_b, _ = ls.borrow_book_by_patron("111111", 1)
    assert ok_b
    # Patron B tries to return
    ok_r, msg_r = ls.return_book_by_patron("222222", 1)
    assert not ok_r and "not currently being borrowed by this patron" in msg_r

def test_r4_return_success_availability_increments(isolated_db):
    ls = _reload_library_service()
    book_id = 2  # "To Kill a Mockingbird", 2 copies
    before = db.get_book_by_id(book_id)["available_copies"]
    ok_b, _ = ls.borrow_book_by_patron("123456", book_id)
    assert ok_b
    ok_r, msg_r = ls.return_book_by_patron("123456", book_id)
    assert ok_r
    after = db.get_book_by_id(book_id)["available_copies"]
    assert after == before  # borrowed once then returned once → availability restored

###############################################################################
# R5: calculate_late_fee_for_book tests  :contentReference[oaicite:14]{index=14}
###############################################################################

def _seed_borrow_exact_overdue(db_book_id: int, patron: str, days_overdue: int):
    """
    Create a borrow record whose due_date is exactly `today - days_overdue`.
    That means:
      - days_overdue = 0 -> due today
      - days_overdue = 3 -> due 3 days ago, etc.
    """
    # Normalize “today” to midnight to avoid time-of-day drift
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    due_dt = today - timedelta(days=days_overdue)
    borrow_dt = due_dt - timedelta(days=14)  # 14-day loan period

    assert db.insert_borrow_record(patron, db_book_id, borrow_dt, due_dt)
    assert db.update_book_availability(db_book_id, -1)

def _fee_r5(days_overdue: int) -> float:
    """
    R5 tiered fee: $0.50/day for first 7 days, then $1/day after day 7, cap $15.00  :contentReference[oaicite:16]{index=16}
    """
    if days_overdue <= 0:
        return 0.0
    first = min(days_overdue, 7) * 0.50
    rest = max(days_overdue - 7, 0) * 1.00
    fee = first + rest
    return min(fee, 15.00)

@pytest.mark.parametrize("days_overdue", [0, 3, 7, 8, 20, 40])
def test_r5_fee_schedule(isolated_db, days_overdue):
    ls = _reload_library_service()
    assert db.insert_book("Fee Book", "Calc", "1234567890129", 1, 1)
    book = db.get_book_by_isbn("1234567890129")
    patron = "999999"

    _seed_borrow_exact_overdue(book["id"], patron, days_overdue)

    result = ls.calculate_late_fee_for_book(patron, book["id"])
    expected_fee = round(_fee_r5(days_overdue), 2)

    assert result["days_overdue"] == days_overdue
    assert abs(result["fee_amount"] - expected_fee) < 1e-6

def test_r5_invalid_inputs_and_not_borrowed(isolated_db):
    ls = _reload_library_service()
    # Invalid patron
    r1 = ls.calculate_late_fee_for_book("12A456", 1)
    assert r1["status"].lower().startswith("invalid patron")
    # Book not found
    r2 = ls.calculate_late_fee_for_book("123456", 9999)
    assert r2["status"].lower().startswith("book not found")
    # Not currently borrowed
    r3 = ls.calculate_late_fee_for_book("123456", 1)
    assert r3["status"].lower().startswith("book not currently borrowed")

###############################################################################
# R6: search_books_in_catalog tests  :contentReference[oaicite:17]{index=17}
###############################################################################

def test_r6_search_validation_and_empty(isolated_db):
    ls = _reload_library_service()
    assert ls.search_books_in_catalog("", "title") == []
    assert ls.search_books_in_catalog("   ", "author") == []

def test_r6_search_title_partial_casefold(isolated_db):
    ls = _reload_library_service()
    res = ls.search_books_in_catalog("great", "title")
    assert any("great gatsby" in b["title"].lower() for b in res)

def test_r6_search_author_partial_casefold(isolated_db):
    ls = _reload_library_service()
    res = ls.search_books_in_catalog("harper", "author")
    assert any("harper lee" in f'{b["author"]}'.lower() for b in res)

def test_r6_search_isbn_exact_ignoring_separators(isolated_db):
    ls = _reload_library_service()
    res = ls.search_books_in_catalog("978-0451524935", "isbn")
    assert len(res) == 1 and res[0]["isbn"] == "9780451524935"

def test_r6_search_all_type_fallback(isolated_db):
    ls = _reload_library_service()
    # Unknown type should behave like "all"
    res = ls.search_books_in_catalog("orwell", "unknown_type")
    assert any("orwell" in f'{b["author"]}'.lower() for b in res)

###############################################################################
# R7: get_patron_status_report tests  :contentReference[oaicite:18]{index=18}
###############################################################################

def test_r7_invalid_patron_id(isolated_db):
    ls = _reload_library_service()
    report = ls.get_patron_status_report("abc123")
    assert report["status"].lower().startswith("invalid patron")
    assert report["borrowed_count"] == 0
    assert report["remaining_allowance"] == 5

def test_r7_report_counts_overdue_and_next_due(isolated_db):
    ls = _reload_library_service()
    patron = "777777"  # fresh patron so seed doesn't add hidden loans

    # Normalize "today" to midnight
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # Book A overdue by 2 days
    bA = db.get_book_by_isbn("9780743273565")  # Gatsby (3 copies in seed)
    borrow_dt_A = today - timedelta(days=14 + 2)
    due_dt_A    = today - timedelta(days=2)
    assert db.insert_borrow_record(patron, bA["id"], borrow_dt_A, due_dt_A)
    assert db.update_book_availability(bA["id"], -1)

    # Book B due in 3 days (not overdue)
    bB = db.get_book_by_isbn("9780061120084")  # Mockingbird (2 copies in seed)
    borrow_dt_B = today - timedelta(days=14 - 3)
    due_dt_B    = today + timedelta(days=3)
    assert db.insert_borrow_record(patron, bB["id"], borrow_dt_B, due_dt_B)
    assert db.update_book_availability(bB["id"], -1)

    report = ls.get_patron_status_report(patron)
    assert report["status"] == "OK"
    assert report["borrowed_count"] == 2          # ✅ now exactly the two we created
    assert report["remaining_allowance"] == 3
    assert report["overdue_count"] == 1
    assert report["next_due_date"] == min(due_dt_A, due_dt_B).isoformat()
    assert len(report["borrowed_books"]) == 2
