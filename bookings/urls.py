from django.urls import path

from .views import AvailableLSAListView, BookingCreateView, PaymentWebhookView

urlpatterns = [
    path("lsas/available/", AvailableLSAListView.as_view(), name="lsa-available"),
    path("bookings/", BookingCreateView.as_view(), name="booking-create"),
    path(
        "payments/webhook/", PaymentWebhookView.as_view(), name="payment-webhook"
    ),
]
