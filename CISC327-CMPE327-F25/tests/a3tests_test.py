import pytest
from unittest.mock import Mock

from services.library_service import (
    add_book_to_catalog,
    borrow_book_by_patron,
    return_book_by_patron,
    pay_late_fees,
    refund_late_fee_payment,
)

from services.payment_service import PaymentGateway

# ----- pay_late_fees tests -----

# Test successful payment
def test_late_fee_successful_payment(mocker):

    mock_calc = mocker.patch(   # Stub calculate_late_fee_for_book
        "services.library_service.calculate_late_fee_for_book",
        return_value={"fee_amount": 5.00, "days_overdue": 3, "status": "OK"},
    )
    mock_get_book = mocker.patch(   # Stub get_book_by_id
        "services.library_service.get_book_by_id",
        return_value={"id": 1, "title": "Test Book"},
    )

    # Mocked payment gateway accepting payment
    gateway_mock = Mock(spec=PaymentGateway)   
    gateway_mock.process_payment.return_value = (True, "txn_123", "Approved")

    success, message, txn_id = pay_late_fees("123456", 1, gateway_mock)

    assert success is True
    assert "Payment successful" in message
    assert txn_id == "txn_123"

    mock_calc.assert_called_once_with("123456", 1)
    mock_get_book.assert_called_once_with(1)

    # Call gateway mock
    gateway_mock.process_payment.assert_called_once_with(
        patron_id = "123456",
        amount = 5.00,
        description = "Late fees for 'Test Book'",
    )

# Test payment denied by gateway
def test_payment_denied_by_gateway(mocker):

    mocker.patch(   # Stub calculate_late_fee_for_book
        "services.library_service.calculate_late_fee_for_book",
        return_value={"fee_amount": 5.00, "days_overdue": 3, "status": "OK"},
    )
    mocker.patch(   # Stub get_book_by_id
        "services.library_service.get_book_by_id",
        return_value={"id": 1, "title": "Test Book"},
    )

    # Mock payment gateway denying payment
    gateway_mock = Mock(spec=PaymentGateway)
    gateway_mock.process_payment.return_value = (False, "txn_999", "Card declined")

    success, message, txn_id = pay_late_fees("123456", 1, gateway_mock)

    assert success is False
    assert "Payment failed" in message
    assert txn_id is None

    # Call gateway mock
    gateway_mock.process_payment.assert_called_once_with(
        patron_id="123456",
        amount=5.00,
        description="Late fees for 'Test Book'",
    )

# Test invalid patron ID (verify mock, NOT called)
def test_invalid_patron_id(mocker):

    mock_calc = mocker.patch(   # Stub calculate_late_fee_for_book
        "services.library_service.calculate_late_fee_for_book",
    )
    mock_get_book = mocker.patch(   # Stub get_book_by_id
        "services.library_service.get_book_by_id",
    )

    gateway_mock = Mock(spec=PaymentGateway)

    success, message, txn_id = pay_late_fees("ABC123", 1, gateway_mock)

    assert success is False
    assert "Invalid patron ID" in message
    assert txn_id is None

    mock_calc.assert_not_called()
    mock_get_book.assert_not_called()
    gateway_mock.process_payment.assert_not_called()

# Test zero late fees (verify mock, NOT called)
def test_zero_late_fees(mocker):

    mock_calc = mocker.patch(   # Stub calculate_late_fee_for_book
        "services.library_service.calculate_late_fee_for_book",
        return_value={"fee_amount": 0.00, "days_overdue": 0, "status": "OK"},
    )
    mock_get_book = mocker.patch(   # Stub get_book_by_id
        "services.library_service.get_book_by_id",
    )

    gateway_mock = Mock(spec=PaymentGateway)

    success, message, txn_id = pay_late_fees("123456", 1, gateway_mock)

    assert success is False
    assert "No late fees" in message
    assert txn_id is None

    mock_calc.assert_called_once_with("123456", 1)
    mock_get_book.assert_not_called()
    gateway_mock.process_payment.assert_not_called()

# Test network error exception handling
def test_network_error_handling(mocker):

    mocker.patch(   # Stub calculate_late_fee_for_book
        "services.library_service.calculate_late_fee_for_book",
        return_value={"fee_amount": 5.00, "days_overdue": 3, "status": "OK"},
    )
    mocker.patch(   # Stub get_book_by_id
        "services.library_service.get_book_by_id",
        return_value={"id": 1, "title": "Test Book"},
    )

    # Mock payment gateway raising exception
    gateway_mock = Mock(spec=PaymentGateway)
    gateway_mock.process_payment.side_effect = Exception("Network error")

    success, message, txn_id = pay_late_fees("123456", 1, gateway_mock)

    assert success is False
    assert "Payment processing error" in message
    assert txn_id is None

    # Call gateway mock
    gateway_mock.process_payment.assert_called_once_with(
        patron_id="123456",
        amount=5.00,
        description="Late fees for 'Test Book'",
    )

# ----- refund_late_fee_payment tests -----

# Test successful refund
def test_successful_refund(mocker):

    # Mocked payment gateway accepting refund
    gateway_mock = Mock(spec=PaymentGateway)
    gateway_mock.refund_payment.return_value = (True, "Refund successful")

    success, message = refund_late_fee_payment("txn_123", 5.00, gateway_mock)

    assert success is True
    assert "Refund successful" in message

    # Call gateway mock
    gateway_mock.refund_payment.assert_called_once_with(
        "txn_123",
        5.00,
    )

# Test invalid transaction ID rejection
def test_invalid_transaction_id(mocker):

    # Mocked payment gateway rejecting refund
    gateway_mock = Mock(spec=PaymentGateway)

    success, message = refund_late_fee_payment("invalid_txn", 5.00, gateway_mock)

    assert success is False
    assert "Invalid transaction ID" in message
    gateway_mock.refund_payment.assert_not_called()

# Test invalid refund amounts (negative, zero, exceeds $15 maximum)
def test_invalid_refund_amounts(mocker):

    gateway_mock = Mock(spec=PaymentGateway)

    # Negative amount
    success, message = refund_late_fee_payment("txn_123", -5.00, gateway_mock)
    assert success is False
    assert "Refund amount must be greater than 0." in message

    # Zero amount
    success, message = refund_late_fee_payment("txn_123", 0.00, gateway_mock)
    assert success is False
    assert "Refund amount must be greater than 0." in message

    # Exceeds $15 maximum
    success, message = refund_late_fee_payment("txn_123", 20.00, gateway_mock)
    assert success is False
    assert "Refund amount exceeds maximum late fee." in message

    gateway_mock.refund_payment.assert_not_called()

# ----- Tests to boost coverage -----
def test_add_book_db_failure(mocker):

    mocker.patch("services.library_service.get_book_by_isbn", return_value=None)
 
    mock_insert = mocker.patch(
        "services.library_service.insert_book",
        return_value=False,
    )

    success, message = add_book_to_catalog(
        "Test Book", "Author Name", "1234567890123", 3
    )

    assert success is False
    assert "database error" in message.lower()
    mock_insert.assert_called_once()

def test_borrow_book_db_error_on_insert(mocker):

    mocker.patch(
        "services.library_service.get_book_by_id",
        return_value={"id": 1, "title": "Test", "available_copies": 1},
    )
    mocker.patch("services.library_service.get_patron_borrow_count", return_value=0)

    mock_insert = mocker.patch(
        "services.library_service.insert_borrow_record",
        return_value=False,
    )
    mock_update = mocker.patch("services.library_service.update_book_availability")

    success, message = borrow_book_by_patron("123456", 1)

    assert success is False
    assert "creating borrow record" in message.lower()
    mock_insert.assert_called_once()
    mock_update.assert_not_called()


def test_borrow_book_db_error_on_update_availability(mocker):
    mocker.patch(
        "services.library_service.get_book_by_id",
        return_value={"id": 1, "title": "Test", "available_copies": 1},
    )
    mocker.patch("services.library_service.get_patron_borrow_count", return_value=0)

    mocker.patch("services.library_service.insert_borrow_record", return_value=True)

    mock_update = mocker.patch(
        "services.library_service.update_book_availability",
        return_value=False,
    )

    success, message = borrow_book_by_patron("123456", 1)

    assert success is False
    assert "updating book availability" in message.lower()
    mock_update.assert_called_once()

def test_return_book_with_late_fee(mocker):
    mocker.patch(
        "services.library_service.get_book_by_id",
        return_value={"id": 1, "title": "Test Book"},
    )
    mocker.patch(
        "services.library_service.calculate_late_fee_for_book",
        return_value={"fee_amount": 3.50, "days_overdue": 2, "status": "OK"},
    )
    mocker.patch(
        "services.library_service.update_borrow_record_return_date",
        return_value=True,
    )
    mocker.patch(
        "services.library_service.update_book_availability",
        return_value=True,
    )

    success, message = return_book_by_patron("123456", 1)

    assert success is True
    assert "late by 2 day(s)" in message.lower()
    assert "$3.50" in message

def test_return_book_db_error_on_update_availability(mocker):
    mocker.patch(
        "services.library_service.get_book_by_id",
        return_value={"id": 1, "title": "Test Book"},
    )
    mocker.patch(
        "services.library_service.calculate_late_fee_for_book",
        return_value={"fee_amount": 0.0, "days_overdue": 0, "status": "OK"},
    )
    mocker.patch(
        "services.library_service.update_borrow_record_return_date",
        return_value=True,
    )
    mock_update = mocker.patch(
        "services.library_service.update_book_availability",
        return_value=False,
    )

    success, message = return_book_by_patron("123456", 1)

    assert success is False
    assert "database error" in message.lower()
    mock_update.assert_called_once()

def test_pay_late_fees_unable_to_calculate_fee(mocker):
    mocker.patch(
        "services.library_service.calculate_late_fee_for_book",
        return_value={},  # missing 'fee_amount'
    )

    gateway_mock = Mock(spec=PaymentGateway)

    success, message, txn_id = pay_late_fees("123456", 1, gateway_mock)

    assert success is False
    assert "unable to calculate late fees" in message.lower()
    assert txn_id is None
    gateway_mock.process_payment.assert_not_called()

def test_pay_late_fees_book_not_found(mocker):
    mocker.patch(
        "services.library_service.calculate_late_fee_for_book",
        return_value={"fee_amount": 5.00, "days_overdue": 3, "status": "OK"},
    )
    mocker.patch(
        "services.library_service.get_book_by_id",
        return_value=None,  # Book not found
    )

    gateway_mock = Mock(spec=PaymentGateway)

    success, message, txn_id = pay_late_fees("123456", 1, gateway_mock)

    assert success is False
    assert "book not found" in message.lower()
    assert txn_id is None
    gateway_mock.process_payment.assert_not_called()

def test_pay_late_fees_use_default_gateways_when_none(mocker):
    mocker.patch(
        "services.library_service.calculate_late_fee_for_book",
        return_value={"fee_amount": 5.00, "days_overdue": 3, "status": "OK"},
    )
    mocker.patch(
        "services.library_service.get_book_by_id",
        return_value={"id": 1, "title": "Test Book"},
    )

    # Mock the default payment gateway inside the library_service module
    default_gateway_mock = Mock(spec=PaymentGateway)
    default_gateway_mock.process_payment.return_value = (True, "txn_456", "Approved")

    mocker.patch(
        "services.library_service.PaymentGateway",
        return_value=default_gateway_mock,
    )

    success, message, txn_id = pay_late_fees("123456", 1, None)

    assert success is True
    assert "Payment successful" in message
    assert txn_id == "txn_456"

    default_gateway_mock.process_payment.assert_called_once_with(
        patron_id="123456",
        amount=5.00,
        description="Late fees for 'Test Book'",
    )