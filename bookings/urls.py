from django.urls import path

from .views import AvailableLSAListView, BookingCreateView, PaymentWebhookView

urlpatterns = [
    # GET /api/v1/lsas/search/ — matches the hiring brief's required path.
    path("lsas/search/", AvailableLSAListView.as_view(), name="lsa-search"),
    # POST /api/v1/bookings/
    path("bookings/", BookingCreateView.as_view(), name="booking-create"),
    # POST /api/v1/payments/webhook/
    path(
        "payments/webhook/", PaymentWebhookView.as_view(), name="payment-webhook"
    ),
]
