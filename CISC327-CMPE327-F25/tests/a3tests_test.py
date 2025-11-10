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

    gateway_mock = Mock(spec=PaymentGateway)
    gateway_mock.process_payment.return_value = (True, "txn_123", "Approved")

    success, message, txn_id = pay_late_fees("123456", 1, gateway_mock)

    assert success is True
    assert "Payment successful" in message
    assert txn_id == "txn_123"

    mock_calc.assert_called_once_with("123456", 1)
    mock_get_book.assert_called_once_with(1)

    gateway_mock.process_payment.assert_called_once_with(
        patron_id = "123456",
        amount = 5.00,
        description = "Late fees for 'Test Book'",
    )

# Test payment denied by gateway



# Test invalid patron ID (verify mock NOT called)

# Test zero late fees (verify mock NOT called)

# Test network error exception handling

# ----- refund_late_fee_payment tests -----

# Test successful refun

# Test invalid transaction ID rejection

# Test invalid refund amounts (negative, zero, exceeds $15 maximum)
