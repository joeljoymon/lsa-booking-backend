from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from bookings.models import LSA, Booking

pytestmark = pytest.mark.django_db


def test_available_lsas_excludes_busy_lsa(api_client, parent, lsa, other_lsa):
    start = timezone.now() + timedelta(days=1)
    end = start + timedelta(hours=1)
    Booking.objects.create(
        parent=parent,
        lsa=lsa,
        start_time=start,
        end_time=end,
        status=Booking.Status.CONFIRMED,
    )

    url = reverse("lsa-search")
    response = api_client.get(
        url, {"start": start.isoformat(), "end": end.isoformat()}
    )

    assert response.status_code == 200
    names = [item["name"] for item in response.data]
    assert lsa.name not in names
    assert other_lsa.name in names


def test_available_lsas_constant_query_count(
    api_client, parent, django_assert_num_queries
):
    """
    Regardless of how many LSAs/bookings exist, listing available LSAs
    should issue a fixed, small number of queries (not one per LSA),
    proving the endpoint does not suffer from the N+1 problem.
    """
    start = timezone.now() + timedelta(days=1)
    end = start + timedelta(hours=1)

    for i in range(10):
        created_lsa = LSA.objects.create(
            name=f"LSA {i}", email=f"lsa{i}@example.com", subject="Mathematics"
        )
        Booking.objects.create(
            parent=parent,
            lsa=created_lsa,
            start_time=start + timedelta(days=i),
            end_time=start + timedelta(days=i, hours=1),
            status=Booking.Status.CONFIRMED,
        )

    url = reverse("lsa-search")
    # 1 query: main LSA select, with the "busy LSA ids" resolved as a
    # correlated subquery inside the same SQL statement (not a separate
    # round-trip). 1 query: prefetch_related fetch of related bookings
    # for all matching LSAs at once, instead of one query per LSA.
    with django_assert_num_queries(2):
        response = api_client.get(
            url, {"start": start.isoformat(), "end": end.isoformat()}
        )
    assert response.status_code == 200
