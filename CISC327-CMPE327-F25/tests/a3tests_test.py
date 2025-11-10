import pytest
from unittest.mock import Mock

from services.library_service import (
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
