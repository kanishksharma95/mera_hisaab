"""
Razorpay gateway wrapper — the single boundary between Mera Hisaab and the
Razorpay SDK. Everything here works in test mode with ``rzp_test_*`` keys and
in production with live keys; nothing else in the codebase imports ``razorpay``
directly, so the gateway can be swapped or mocked in one place.

Amounts cross this boundary in the app's natural unit (rupees, ``Decimal``);
conversion to paise (Razorpay's integer unit) happens here.
"""
from decimal import Decimal

from django.conf import settings

from .models import SAAS_PLANS


class GatewayNotConfigured(RuntimeError):
    """Raised when a gateway call is attempted without API keys set."""


def is_configured():
    """True when Razorpay keys are present (features stay hidden otherwise)."""
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


def _client():
    if not is_configured():
        raise GatewayNotConfigured(
            "Razorpay keys are not set. Add RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET."
        )
    import razorpay  # local import so the app runs without the package/keys

    return razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )


def to_paise(amount):
    """Convert a rupee Decimal/number to an integer paise amount."""
    return int((Decimal(str(amount)) * 100).to_integral_value())


# --------------------------------------------------------------------------- #
# Customer invoice collection (Orders + Checkout)
# --------------------------------------------------------------------------- #
def create_order(*, amount, receipt, notes=None, currency="INR"):
    """Create a Razorpay order for a one-time payment. ``amount`` in rupees."""
    return _client().order.create({
        "amount": to_paise(amount),
        "currency": currency,
        "receipt": receipt[:40],
        "payment_capture": 1,
        "notes": notes or {},
    })


def verify_payment_signature(*, order_id, payment_id, signature):
    """Verify a Checkout success callback. Raises on tampering."""
    _client().utility.verify_payment_signature({
        "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": signature,
    })


# --------------------------------------------------------------------------- #
# Webhooks (source of truth for both flows)
# --------------------------------------------------------------------------- #
def verify_webhook_signature(*, body, signature):
    """Verify a raw webhook body against the configured webhook secret.

    ``body`` is the exact bytes/str received. Raises on mismatch.
    """
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    _client().utility.verify_webhook_signature(
        body, signature, settings.RAZORPAY_WEBHOOK_SECRET
    )


# --------------------------------------------------------------------------- #
# SaaS subscription billing (Plans + Subscriptions)
# --------------------------------------------------------------------------- #
def ensure_plan(plan_code):
    """Create (or return) a Razorpay Plan for one of our SAAS_PLANS.

    Returns the Razorpay plan id. In a real deployment you would create these
    once and cache the ids; we create on demand so test mode is zero-setup.
    """
    spec = SAAS_PLANS.get(plan_code)
    if not spec:
        raise ValueError(f"Unknown plan '{plan_code}'.")
    plan = _client().plan.create({
        "period": spec["period"],
        "interval": spec["interval"],
        "item": {
            "name": spec["name"],
            "amount": to_paise(spec["amount"]),
            "currency": "INR",
        },
        "notes": {"plan_code": plan_code},
    })
    return plan["id"]


def create_subscription(*, plan_id, total_count=12, notes=None):
    """Create a Razorpay subscription against a plan id."""
    return _client().subscription.create({
        "plan_id": plan_id,
        "total_count": total_count,
        "customer_notify": 1,
        "notes": notes or {},
    })
