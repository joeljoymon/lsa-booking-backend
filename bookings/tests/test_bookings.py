from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking

pytestmark = pytest.mark.django_db


def test_booking_creation_success(api_client, parent, lsa):
    start = timezone.now() + timedelta(days=1)
    end = start + timedelta(hours=1)

    response = api_client.post(
        reverse("booking-create"),
        {
            "parent": parent.id,
            "lsa": lsa.id,
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
        },
        format="json",
    )

    assert response.status_code == 201
    assert Booking.objects.count() == 1
    assert Booking.objects.first().status == Booking.Status.PENDING


def test_overlapping_booking_is_rejected(api_client, confirmed_booking):
    # Same LSA, overlapping window with the existing confirmed_booking fixture.
    overlap_start = confirmed_booking.start_time + timedelta(minutes=30)
    overlap_end = overlap_start + timedelta(hours=1)

    response = api_client.post(
        reverse("booking-create"),
        {
            "parent": confirmed_booking.parent_id,
            "lsa": confirmed_booking.lsa_id,
            "start_time": overlap_start.isoformat(),
            "end_time": overlap_end.isoformat(),
        },
        format="json",
    )

    assert response.status_code == 400
    assert Booking.objects.count() == 1


def test_non_overlapping_booking_for_same_lsa_is_accepted(
    api_client, confirmed_booking
):
    # Starts exactly when the existing booking ends -> no overlap.
    new_start = confirmed_booking.end_time
    new_end = new_start + timedelta(hours=1)

    response = api_client.post(
        reverse("booking-create"),
        {
            "parent": confirmed_booking.parent_id,
            "lsa": confirmed_booking.lsa_id,
            "start_time": new_start.isoformat(),
            "end_time": new_end.isoformat(),
        },
        format="json",
    )

    assert response.status_code == 201
    assert Booking.objects.count() == 2


def test_invalid_time_range_is_rejected(api_client, parent, lsa):
    start = timezone.now() + timedelta(days=1)
    end = start - timedelta(hours=1)  # end before start

    response = api_client.post(
        reverse("booking-create"),
        {
            "parent": parent.id,
            "lsa": lsa.id,
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
        },
        format="json",
    )

    assert response.status_code == 400
