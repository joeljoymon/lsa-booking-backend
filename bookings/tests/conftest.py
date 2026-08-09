from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from bookings.models import LSA, Booking, Parent, Payment


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def parent(db):
    return Parent.objects.create(name="Asha Rao", email="asha@example.com")


@pytest.fixture
def lsa(db):
    return LSA.objects.create(
        name="Rahul Mehta", email="rahul@example.com", subject="Mathematics"
    )


@pytest.fixture
def other_lsa(db):
    return LSA.objects.create(
        name="Priya Nair", email="priya@example.com", subject="Science"
    )


@pytest.fixture
def confirmed_booking(db, parent, lsa):
    start = timezone.now() + timedelta(days=1)
    booking = Booking.objects.create(
        parent=parent,
        lsa=lsa,
        start_time=start,
        end_time=start + timedelta(hours=1),
        status=Booking.Status.CONFIRMED,
    )
    return booking


@pytest.fixture
def pending_payment(db, parent, lsa):
    start = timezone.now() + timedelta(days=2)
    booking = Booking.objects.create(
        parent=parent,
        lsa=lsa,
        start_time=start,
        end_time=start + timedelta(hours=1),
        status=Booking.Status.PENDING,
    )
    payment = Payment.objects.create(booking=booking, amount=500)
    return payment
