"""
Mock third-party payment gateway integration.

Simulates the outbound call a real booking system makes to a payment
provider (Stripe/Razorpay-style) to initiate a payment after a booking is
created. Uses httpbin.org's /post endpoint as a stand-in "mock gateway" —
it simply echoes back whatever JSON payload it receives with a 200,
letting us exercise a real HTTP round trip without needing a real gateway
account or API key.

The gateway URL is configurable via the PAYMENT_GATEWAY_URL setting, so a
real gateway endpoint can be swapped in without touching this module.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_GATEWAY_URL = "https://httpbin.org/post"
REQUEST_TIMEOUT_SECONDS = 5


class PaymentGatewayError(Exception):
    """Raised when the mock payment gateway can't be reached or errors out."""


def initiate_payment(payment):
    """
    Notify the (mock) payment gateway that a new payment should be
    initiated for the given Payment instance.

    This is a "soft" integration by design: if the gateway call fails
    (timeout, network error, non-2xx response), we log the failure and
    raise PaymentGatewayError, but the caller (BookingCreateView) chooses
    NOT to fail the booking itself over a downstream gateway hiccup — the
    Payment stays in PENDING and the source of truth for final payment
    status remains the webhook (payments/webhook/), which the real
    gateway calls back independently once it resolves the payment.
    """
    url = getattr(settings, "PAYMENT_GATEWAY_URL", DEFAULT_GATEWAY_URL)
    payload = {
        "reference_id": str(payment.reference_id),
        "amount": str(payment.amount),
        "booking_id": payment.booking_id,
    }

    try:
        response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.exceptions.Timeout as exc:
        logger.error(
            "Payment gateway timed out for payment %s", payment.reference_id
        )
        raise PaymentGatewayError("Gateway request timed out") from exc
    except requests.exceptions.ConnectionError as exc:
        logger.error(
            "Could not reach payment gateway for payment %s: %s",
            payment.reference_id,
            exc,
        )
        raise PaymentGatewayError("Gateway unreachable") from exc
    except requests.exceptions.RequestException as exc:
        logger.error(
            "Payment gateway request failed for payment %s: %s",
            payment.reference_id,
            exc,
        )
        raise PaymentGatewayError(str(exc)) from exc

    logger.info(
        "Payment gateway initiated successfully for payment %s (status %s)",
        payment.reference_id,
        response.status_code,
    )
    return response.json()
