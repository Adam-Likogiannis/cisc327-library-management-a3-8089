"""
Library Service Module - Business Logic Functions
Contains all the core business logic for the Library Management System
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from database import (
    get_book_by_id, get_book_by_isbn, get_patron_borrow_count,
    insert_book, insert_borrow_record, update_book_availability,
    update_borrow_record_return_date, get_all_books,
    get_patron_borrowed_books,
)

from services.payment_service import PaymentGateway

def add_book_to_catalog(title: str, author: str, isbn: str, total_copies: int) -> Tuple[bool, str]:
    """
    Add a new book to the catalog.
    Implements R1: Book Catalog Management
    
    Args:
        title: Book title (max 200 chars)
        author: Book author (max 100 chars)
        isbn: 13-digit ISBN
        total_copies: Number of copies (positive integer)
        
    Returns:
        tuple: (success: bool, message: str)
    """
    # Input validation
    if not title or not title.strip():
        return False, "Title is required."
    
    if len(title.strip()) > 200:
        return False, "Title must be less than 200 characters."
    
    if not author or not author.strip():
        return False, "Author is required."
    
    if len(author.strip()) > 100:
        return False, "Author must be less than 100 characters."
    
    if len(isbn) != 13:
        return False, "ISBN must be exactly 13 digits."
    
    if not isinstance(total_copies, int) or total_copies <= 0:
        return False, "Total copies must be a positive integer."
    
    # Check for duplicate ISBN
    existing = get_book_by_isbn(isbn)
    if existing:
        return False, "A book with this ISBN already exists."
    
    # Insert new book
    success = insert_book(title.strip(), author.strip(), isbn, total_copies, total_copies)
    if success:
        return True, f'Book "{title.strip()}" has been successfully added to the catalog.'
    else:
        return False, "Database error occurred while adding the book."

def borrow_book_by_patron(patron_id: str, book_id: int) -> Tuple[bool, str]:
    """
    Allow a patron to borrow a book.
    Implements R3 as per requirements  
    
    Args:
        patron_id: 6-digit library card ID
        book_id: ID of the book to borrow
        
    Returns:
        tuple: (success: bool, message: str)
    """
    # Validate patron ID
    if not patron_id or not patron_id.isdigit() or len(patron_id) != 6:
        return False, "Invalid patron ID. Must be exactly 6 digits."
    
    # Check if book exists and is available
    book = get_book_by_id(book_id)
    if not book:
        return False, "Book not found."
    
    if book['available_copies'] <= 0:
        return False, "This book is currently not available."
    
    # Check patron's current borrowed books count
    current_borrowed = get_patron_borrow_count(patron_id)
    
    if current_borrowed > 5:
        return False, "You have reached the maximum borrowing limit of 5 books."
    
    # Create borrow record
    borrow_date = datetime.now()
    due_date = borrow_date + timedelta(days=14)
    
    # Insert borrow record and update availability
    borrow_success = insert_borrow_record(patron_id, book_id, borrow_date, due_date)
    if not borrow_success:
        return False, "Database error occurred while creating borrow record."
    
    availability_success = update_book_availability(book_id, -1)
    if not availability_success:
        return False, "Database error occurred while updating book availability."
    
    return True, f'Successfully borrowed "{book["title"]}". Due date: {due_date.strftime("%Y-%m-%d")}.'

def return_book_by_patron(patron_id: str, book_id: int) -> Tuple[bool, str]:
    """
    Process book return by a patron.
    Implements R4 as per requirements

    Args: 
        patron_id: 6-digit library card ID
        book_id: ID of the book to borrow
        
    Returns:
        tuple: (success: bool, message: str)
    """

    # Validate book
    book = get_book_by_id(book_id)
    if not book:
        return False, "Book not found."
    
    # Calculate late fee first (while book is still marked borrowed)
    late = calculate_late_fee_for_book(patron_id, book_id)
    fee = late.get("fee_amount", 0.0)
    days = late.get("days_overdue", 0)

    # Now mark book as returned
    return_date = datetime.now()
    updated = update_borrow_record_return_date(patron_id, book_id, return_date)
    if not updated:
        return False, "This book is not currently being borrowed by this patron."

    # Update availability
    if not update_book_availability(book_id, +1):
        return False, "Database error occurred while updating book availability."

    # Construct message
    if fee > 0:
        return True, (
            f'Return processed for "{book["title"]}". '
            f'Late by {days} day(s). Fee due: ${fee:.2f}.'
        )
    else:
        return True, f'Return processed for \"{book['title']}\". No late fees owed." '

def calculate_late_fee_for_book(patron_id: str, book_id: int) -> dict:
    """
    R5 — Late fee (single-function; uses only existing database.py functions):
      - $0.50/day for the first 7 overdue days
      - $1.00/day after day 7
      - Cap at $15.00 total
    Returns: { fee_amount: float(2dp), days_overdue: int, status: str }
    """
    from datetime import datetime
    from decimal import Decimal, ROUND_HALF_UP
    import database as db  # local import to avoid circulars

    # --- validation ---
    if not (isinstance(patron_id, str) and patron_id.isdigit() and len(patron_id) == 6):
        return {"fee_amount": 0.00, "days_overdue": 0, "status": "Invalid patron ID"}

    book = db.get_book_by_id(book_id)
    if not book:
        return {"fee_amount": 0.00, "days_overdue": 0, "status": "Book not found"}

    # --- find the active borrow record using EXISTING db.py helper ---
    # get_patron_borrowed_books returns ONLY active loans (return_date IS NULL)
    # and includes due_date as a datetime already.
    borrowed = db.get_patron_borrowed_books(patron_id)  # existing function
    active = next((r for r in borrowed if int(r.get("book_id", -1)) == int(book_id)), None)
    if not active:
        return {"fee_amount": 0.00, "days_overdue": 0, "status": "Book not currently borrowed"}

    due_dt = active["due_date"]  # already a datetime
    # compute days_overdue using date-only comparison to avoid off-by-one with time-of-day
    today = datetime.now().date()
    days_overdue = max((today - due_dt.date()).days, 0)

    # --- tiered fee with cap ---
    first = min(days_overdue, 7) * Decimal("0.50")
    rest  = max(days_overdue - 7, 0) * Decimal("1.00")
    fee   = min(first + rest, Decimal("15.00"))
    fee   = fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "fee_amount": float(fee),
        "days_overdue": int(days_overdue),
        "status": "OK",
    }



def search_books_in_catalog(search_term: str, search_type: str) -> List[Dict]:
    """
    Search for books in the catalog.
    
    Implements R6 as per requirements
    """
    
    if not isinstance(search_term, str) or not search_term.strip():
        return[]
    
    term = search_term.strip()
    term_fold = term.casefold()

    allowed_types = {"title", "author", "isbn", "all"}
    stype = (search_type or "all").lower()
    if stype not in allowed_types:
        stype = "all"

    # Fetch books from the database layer
    books = get_all_books()

     # Normalizers for ISBN comparison (ignore hyphens/spaces)
    def _norm_isbn(s: str) -> str:
        return (s or "").replace("-", "").replace(" ", "")

    norm_term_isbn = _norm_isbn(term)

    def _matches(book: Dict) -> bool:
        title = (book.get("title") or "").casefold()
        author = (book.get("author") or "").casefold()
        isbn = _norm_isbn(str(book.get("isbn") or ""))

        if stype == "title":
            return term_fold in title
        elif stype == "author":
            return term_fold in author
        elif stype == "isbn":
            return norm_term_isbn == isbn
        else:  # all
            return (
                term_fold in title
                or term_fold in author
                or (norm_term_isbn and norm_term_isbn in isbn)
            )

    results = [b for b in books if _matches(b)]

    # Return sorted results
    results.sort(key=lambda b: ((b.get("title") or "").casefold(), (b.get("author") or "").casefold()))
    return results

def get_patron_status_report(patron_id: str) -> Dict:
    """
    Get status report for a patron.
    
    Implements R7 as per requirements
    """

    # Validate patron id
    if not patron_id or not patron_id.isdigit() or len(patron_id) != 6:
        return {
            "patron_id": patron_id,
            "borrowed_count": 0,
            "remaining_allowance": 5,
            "overdue_count": 0,
            "next_due_date": None,
            "borrowed_books": [],
            "status": "Invalid patron ID. Must be exactly 6 digits."
        }
    
    # Get current borrowed items
    borrowed_books_raw: List[Dict] = get_patron_borrowed_books(patron_id)
    borrowed_count: int = get_patron_borrow_count(patron_id)

    # Normalize/augment items for report
    now = datetime.now()
    borrowed_books_report: List[Dict] = []
    overdue_count = 0
    next_due_dt = None

    for item in borrowed_books_raw:
        borrow_dt = item.get("borrow_date")
        due_dt = item.get("due_date")
        is_overdue = bool(item.get("is_overdue"))

        # Compute days_overdue (0 if not overdue)
        days_overdue = 0
        if isinstance(due_dt, datetime):
            if is_overdue:
                days_overdue = max((now - due_dt).days, 0)
            # track earliest upcoming due date
            if next_due_dt is None or due_dt < next_due_dt:
                next_due_dt = due_dt

        if is_overdue:
            overdue_count += 1

        borrowed_books_report.append({
            "book_id": item.get("book_id"),
            "title": item.get("title"),
            "author": item.get("author"),
            "borrow_date": borrow_dt.isoformat() if isinstance(borrow_dt, datetime) else None,
            "due_date": due_dt.isoformat() if isinstance(due_dt, datetime) else None,
            "is_overdue": is_overdue,
            "days_overdue": days_overdue,
        })

    remaining = max(0, 5 - int(borrowed_count or 0))

    return {
        "patron_id": patron_id,
        "borrowed_count": borrowed_count,
        "remaining_allowance": remaining,
        "overdue_count": overdue_count,
        "next_due_date": next_due_dt.isoformat() if isinstance(next_due_dt, datetime) else None,
        "borrowed_books": borrowed_books_report,
        "status": "OK",
    }

def pay_late_fees(patron_id: str, book_id: int, payment_gateway: PaymentGateway = None) -> Tuple[bool, str, Optional[str]]:
    """
    Process payment for late fees using external payment gateway.
    
    NEW FEATURE FOR ASSIGNMENT 3: Demonstrates need for mocking/stubbing
    This function depends on an external payment service that should be mocked in tests.
    
    Args:
        patron_id: 6-digit library card ID
        book_id: ID of the book with late fees
        payment_gateway: Payment gateway instance (injectable for testing)
        
    Returns:
        tuple: (success: bool, message: str, transaction_id: Optional[str])
        
    Example for you to mock:
        # In tests, mock the payment gateway:
        mock_gateway = Mock(spec=PaymentGateway)
        mock_gateway.process_payment.return_value = (True, "txn_123", "Success")
        success, msg, txn = pay_late_fees("123456", 1, mock_gateway)
    """
    # Validate patron ID
    if not patron_id or not patron_id.isdigit() or len(patron_id) != 6:
        return False, "Invalid patron ID. Must be exactly 6 digits.", None
    
    # Calculate late fee first
    fee_info = calculate_late_fee_for_book(patron_id, book_id)
    
    # Check if there's a fee to pay
    if not fee_info or 'fee_amount' not in fee_info:
        return False, "Unable to calculate late fees.", None
    
    fee_amount = fee_info.get('fee_amount', 0.0)
    
    if fee_amount <= 0:
        return False, "No late fees to pay for this book.", None
    
    # Get book details for payment description
    book = get_book_by_id(book_id)
    if not book:
        return False, "Book not found.", None
    
    # Use provided gateway or create new one
    if payment_gateway is None:
        payment_gateway = PaymentGateway()
    
    # Process payment through external gateway
    # THIS IS WHAT YOU SHOULD MOCK IN THEIR TESTS!
    try:
        success, transaction_id, message = payment_gateway.process_payment(
            patron_id=patron_id,
            amount=fee_amount,
            description=f"Late fees for '{book['title']}'"
        )
        
        if success:
            return True, f"Payment successful! {message}", transaction_id
        else:
            return False, f"Payment failed: {message}", None
            
    except Exception as e:
        # Handle payment gateway errors
        return False, f"Payment processing error: {str(e)}", None


def refund_late_fee_payment(transaction_id: str, amount: float, payment_gateway: PaymentGateway = None) -> Tuple[bool, str]:
    """
    Refund a late fee payment (e.g., if book was returned on time but fees were charged in error).
    
    NEW FEATURE FOR ASSIGNMENT 3: Another function requiring mocking
    
    Args:
        transaction_id: Original transaction ID to refund
        amount: Amount to refund
        payment_gateway: Payment gateway instance (injectable for testing)
        
    Returns:
        tuple: (success: bool, message: str)
    """
    # Validate inputs
    if not transaction_id or not transaction_id.startswith("txn_"):
        return False, "Invalid transaction ID."
    
    if amount <= 0:
        return False, "Refund amount must be greater than 0."
    
    if amount > 15.00:  # Maximum late fee per book
        return False, "Refund amount exceeds maximum late fee."
    
    # Use provided gateway or create new one
    if payment_gateway is None:
        payment_gateway = PaymentGateway()
    
    # Process refund through external gateway
    # THIS IS WHAT YOU SHOULD MOCK IN YOUR TESTS!
    try:
        success, message = payment_gateway.refund_payment(transaction_id, amount)
        
        if success:
            return True, message
        else:
            return False, f"Refund failed: {message}"
            
    except Exception as e:
        return False, f"Refund processing error: {str(e)}"
