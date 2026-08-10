from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
import requests

from bookings.services import PaymentGatewayError, initiate_payment

pytestmark = pytest.mark.django_db


@pytest.fixture
def payment(parent, lsa):
    from datetime import timedelta

    from django.utils import timezone

    from bookings.models import Booking, Payment

    start = timezone.now() + timedelta(days=1)
    booking = Booking.objects.create(
        parent=parent,
        lsa=lsa,
        start_time=start,
        end_time=start + timedelta(hours=1),
    )
    return Payment.objects.create(booking=booking, amount=Decimal("500.00"))


@patch("bookings.services.requests.post")
def test_initiate_payment_success(mock_post, payment):
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"echoed": True}
    mock_post.return_value = mock_response

    result = initiate_payment(payment)

    assert result == {"echoed": True}
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["reference_id"] == str(payment.reference_id)
    assert kwargs["json"]["amount"] == str(payment.amount)
    assert kwargs["timeout"] == 5


@patch("bookings.services.requests.post")
def test_initiate_payment_timeout_raises_gateway_error(mock_post, payment):
    mock_post.side_effect = requests.exceptions.Timeout("simulated timeout")

    with pytest.raises(PaymentGatewayError):
        initiate_payment(payment)


@patch("bookings.services.requests.post")
def test_initiate_payment_connection_error_raises_gateway_error(mock_post, payment):
    mock_post.side_effect = requests.exceptions.ConnectionError("simulated down")

    with pytest.raises(PaymentGatewayError):
        initiate_payment(payment)


@patch("bookings.services.requests.post")
def test_initiate_payment_bad_status_raises_gateway_error(mock_post, payment):
    mock_response = Mock()
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        "500 Server Error"
    )
    mock_post.return_value = mock_response

    with pytest.raises(PaymentGatewayError):
        initiate_payment(payment)
