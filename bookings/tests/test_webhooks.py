import pytest
from django.urls import reverse

from bookings.models import Booking, Payment

pytestmark = pytest.mark.django_db


def test_webhook_success_confirms_booking(api_client, pending_payment):
    response = api_client.post(
        reverse("payment-webhook"),
        {"event": "payment.success", "reference_id": pending_payment.reference_id},
        format="json",
    )

    pending_payment.refresh_from_db()
    booking = pending_payment.booking
    booking.refresh_from_db()

    assert response.status_code == 200
    assert pending_payment.status == Payment.Status.SUCCESS
    assert booking.status == Booking.Status.CONFIRMED


def test_webhook_failure_cancels_booking(api_client, pending_payment):
    response = api_client.post(
        reverse("payment-webhook"),
        {"event": "payment.failed", "reference_id": pending_payment.reference_id},
        format="json",
    )

    pending_payment.refresh_from_db()
    booking = pending_payment.booking
    booking.refresh_from_db()

    assert response.status_code == 200
    assert pending_payment.status == Payment.Status.FAILED
    assert booking.status == Booking.Status.CANCELLED


def test_webhook_replay_is_idempotent(api_client, pending_payment):
    url = reverse("payment-webhook")
    payload = {"event": "payment.success", "reference_id": pending_payment.reference_id}

    first = api_client.post(url, payload, format="json")
    second = api_client.post(url, payload, format="json")

    assert first.status_code == 200
    assert second.status_code == 200
    assert "already" in second.data["detail"]
    # Booking/payment state should not have changed on replay.
    pending_payment.refresh_from_db()
    assert pending_payment.status == Payment.Status.SUCCESS


def test_webhook_unknown_reference_returns_404(api_client):
    response = api_client.post(
        reverse("payment-webhook"),
        {"event": "payment.success", "reference_id": "does-not-exist"},
        format="json",
    )
    assert response.status_code == 404
