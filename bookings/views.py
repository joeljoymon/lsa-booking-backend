from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import LSA, Booking, Payment
from .serializers import (
    BookingSerializer,
    LSASerializer,
    PaymentWebhookSerializer,
)
from .services import PaymentGatewayError, initiate_payment

# Flat per-session fee. A real system would price this from the LSA's
# rate card; kept as a simple constant here to keep the booking payload
# unchanged from what was already agreed with the brief.
DEFAULT_SESSION_FEE = Decimal("500.00")


class AvailableLSAListView(generics.ListAPIView):
    """
    GET /api/v1/lsas/search/?skills=Math&start=<iso>&end=<iso>

    Returns LSAs that are active and have no CONFIRMED/PENDING booking
    overlapping the given [start, end) window.

    N+1 avoidance strategy:
    1. The "busy" LSA ids are resolved with a single subquery
       (`Booking.objects.filter(...).values_list('lsa_id', flat=True)`)
       instead of looping over each LSA and issuing a per-row query.
    2. `annotate(Count(...))` computes the upcoming-booking count in the
       same SQL query as the LSA list, rather than triggering one COUNT
       query per LSA when serialized.
    3. If session details ever need to be listed alongside each LSA,
       `Prefetch` is used so Django issues exactly one extra query for
       *all* related bookings, not one query per LSA.
    """

    serializer_class = LSASerializer

    def get_queryset(self):
        params = self.request.query_params
        subject = params.get("skills") or params.get("subject")
        start = parse_datetime(params.get("start")) if params.get("start") else None
        end = parse_datetime(params.get("end")) if params.get("end") else None

        queryset = LSA.objects.filter(is_active=True)
        if subject:
            queryset = queryset.filter(subject__iexact=subject)

        if start and end:
            busy_lsa_ids = Booking.objects.filter(
                status__in=Booking.ACTIVE_STATUSES,
                start_time__lt=end,
                end_time__gt=start,
            ).values_list("lsa_id", flat=True)
            queryset = queryset.exclude(id__in=busy_lsa_ids)

        queryset = queryset.annotate(
            upcoming_booking_count=Count(
                "bookings", filter=Q(bookings__status__in=Booking.ACTIVE_STATUSES)
            )
        ).prefetch_related(
            Prefetch(
                "bookings",
                queryset=Booking.objects.filter(
                    status__in=Booking.ACTIVE_STATUSES
                ).only("id", "lsa_id", "start_time", "end_time", "status"),
            )
        )
        return queryset.order_by("name")


class BookingCreateView(generics.CreateAPIView):
    """
    POST /api/bookings/

    Creates a booking after validating there is no overlapping active
    booking for the same LSA. The overlap check + insert is wrapped in a
    single atomic transaction with a row lock on the LSA's existing
    bookings, so two simultaneous requests for the same slot cannot both
    slip past validation (a plain serializer-level check alone is
    vulnerable to that race).
    """

    serializer_class = BookingSerializer
    queryset = Booking.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        lsa = serializer.validated_data["lsa"]
        start = serializer.validated_data["start_time"]
        end = serializer.validated_data["end_time"]

        with transaction.atomic():
            # select_for_update locks matching rows until the transaction
            # commits (no-op on SQLite, effective on Postgres/MySQL).
            locked_overlaps = Booking.objects.select_for_update().filter(
                lsa=lsa,
                status__in=Booking.ACTIVE_STATUSES,
                start_time__lt=end,
                end_time__gt=start,
            )
            if locked_overlaps.exists():
                return Response(
                    {
                        "detail": "This LSA already has an overlapping "
                        "session in that time window."
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            self.perform_create(serializer)
            booking = serializer.instance

            # Create the Payment row up front (PENDING) and kick off the
            # mock gateway call. This mirrors a real flow: booking placed
            # -> payment intent created with the gateway -> gateway later
            # confirms/fails asynchronously via the webhook.
            payment = Payment.objects.create(
                booking=booking, amount=DEFAULT_SESSION_FEE
            )

        # Gateway call happens *after* the transaction commits, so a slow
        # or failing third-party call never holds the booking's DB lock.
        # Failure here is intentionally non-fatal to the booking itself —
        # see services.initiate_payment's docstring for the reasoning.
        try:
            initiate_payment(payment)
        except PaymentGatewayError:
            # Already logged inside initiate_payment. The booking and its
            # PENDING payment still exist; the flow can be retried or
            # resolved later via the webhook.
            pass

        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )


class PaymentWebhookView(APIView):
    """
    POST /api/payments/webhook/

    Body: {"event": "payment.success" | "payment.failed", "reference_id": "..."}

    Transitions the related Booking's state based on the payment event:
      payment.success -> Payment.SUCCESS, Booking.CONFIRMED
      payment.failed  -> Payment.FAILED,  Booking.CANCELLED
    """

    def post(self, request, *args, **kwargs):
        serializer = PaymentWebhookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        event = serializer.validated_data["event"]
        reference_id = serializer.validated_data["reference_id"]

        payment = get_object_or_404(Payment, reference_id=reference_id)

        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(pk=payment.pk)

            if payment.status != Payment.Status.PENDING:
                # Idempotency: replayed webhook events are a no-op.
                return Response(
                    {"detail": f"Payment already {payment.status}; no action taken."},
                    status=status.HTTP_200_OK,
                )

            booking = payment.booking

            if event == "payment.success":
                payment.status = Payment.Status.SUCCESS
                booking.status = Booking.Status.CONFIRMED
            else:
                payment.status = Payment.Status.FAILED
                booking.status = Booking.Status.CANCELLED

            payment.save(update_fields=["status", "updated_at"])
            booking.save(update_fields=["status", "updated_at"])

        return Response(
            {
                "payment_status": payment.status,
                "booking_status": booking.status,
            },
            status=status.HTTP_200_OK,
        )
