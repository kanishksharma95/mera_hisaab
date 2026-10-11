"""Payment-method helpers + gateway-payment recording (per business)."""
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from .models import DEFAULT_PAYMENT_METHODS, Payment, PaymentMethod

_TWOPLACES = Decimal("0.01")


def _money(value):
    return Decimal(str(value)).quantize(_TWOPLACES, rounding=ROUND_HALF_UP)


def ensure_default_methods(business):
    """Create the default payment methods for a business if it has none.

    Called lazily (e.g. when the POS loads) so existing businesses get methods
    without a data migration, and everything stays editable in the DB.
    """
    if PaymentMethod.objects.for_business(business).exists():
        return
    for order, (name, code, is_cash_like) in enumerate(DEFAULT_PAYMENT_METHODS):
        PaymentMethod.objects.get_or_create(
            business=business,
            code=code,
            defaults={"name": name, "is_cash_like": is_cash_like, "sort_order": order},
        )


def get_credit_method(business):
    """Return this business's credit/udhaar method, if configured."""
    return PaymentMethod.objects.for_business(business).filter(code="credit").first()


def get_online_method(business):
    """Return (creating if needed) the 'Razorpay / Online' method for gateway
    payments, so online receipts land in the cashbook like any other method."""
    method, _ = PaymentMethod.objects.get_or_create(
        business=business,
        code="online",
        defaults={"name": "Razorpay / Online", "is_cash_like": True, "sort_order": 50},
    )
    return method


@transaction.atomic
def apply_gateway_payment_to_sale(
    *, sale, razorpay_payment_id, razorpay_order_id="", amount=None, user=None
):
    """Record a captured Razorpay payment against a sale — idempotently.

    Safe to call from BOTH the browser callback and the webhook (Razorpay may
    also deliver a webhook more than once): the unique razorpay_payment_id makes
    a replay a no-op that returns the already-recorded Payment.

    Updates the sale's paid/due/status and, for a credit sale, pays down the
    customer's udhaar ledger for the covered portion.
    """
    from sales.models import Sale  # local import avoids any import cycle

    business = sale.business
    existing = (
        Payment.objects.for_business(business)
        .filter(razorpay_payment_id=razorpay_payment_id)
        .first()
    )
    if existing:
        return existing

    locked = Sale.objects.select_for_update().get(pk=sale.pk)
    amount = _money(amount if amount is not None else locked.due_amount)
    due_before = locked.due_amount

    payment = Payment.objects.create(
        business=business,
        direction=Payment.Direction.IN,
        method=get_online_method(business),
        amount=amount,
        sale=locked,
        customer=locked.customer,
        reference=f"sale:{locked.id}",
        razorpay_order_id=razorpay_order_id,
        razorpay_payment_id=razorpay_payment_id,
        created_by=user,
    )

    new_paid = min(locked.paid_amount + amount, locked.total)
    locked.paid_amount = new_paid
    locked.due_amount = _money(locked.total - new_paid)
    if locked.due_amount <= 0:
        locked.payment_status = Sale.PaymentStatus.PAID
    elif new_paid > 0:
        locked.payment_status = Sale.PaymentStatus.PARTIAL
    locked.save(
        update_fields=["paid_amount", "due_amount", "payment_status", "updated_at"]
    )

    if locked.customer and due_before > 0:
        from customers.services import record_payment as record_customer_payment

        record_customer_payment(
            customer=locked.customer,
            amount=min(amount, due_before),
            description=f"Online payment for {locked.invoice_number}",
            method="Razorpay",
            reference=f"sale:{locked.id}",
            user=user,
        )

    return payment


# --------------------------------------------------------------------------- #
# SaaS subscriptions
# --------------------------------------------------------------------------- #
def start_subscription(*, business, plan_code, user=None):
    """Create a Razorpay subscription for a business and persist our record.

    Returns (BusinessSubscription, razorpay_subscription_dict). The dict carries
    the ``short_url`` / id the frontend needs to open Checkout.
    """
    from . import gateway
    from .models import SAAS_PLANS, BusinessSubscription

    if plan_code not in SAAS_PLANS:
        raise ValueError(f"Unknown plan '{plan_code}'.")

    plan_id = gateway.ensure_plan(plan_code)
    rzp_sub = gateway.create_subscription(
        plan_id=plan_id,
        notes={"business_id": str(business.id), "plan_code": plan_code},
    )
    sub, _ = BusinessSubscription.objects.update_or_create(
        business=business,
        defaults={
            "plan_code": plan_code,
            "razorpay_plan_id": plan_id,
            "razorpay_subscription_id": rzp_sub["id"],
            "status": rzp_sub.get("status", "created"),
            "created_by": user,
        },
    )
    return sub, rzp_sub


def sync_subscription_status(
    *, razorpay_subscription_id, status, current_period_end=None
):
    """Update a subscription's status from a webhook. No-op if unknown."""
    from .models import BusinessSubscription

    sub = BusinessSubscription.objects.filter(
        razorpay_subscription_id=razorpay_subscription_id
    ).first()
    if sub is None:
        return None
    sub.status = status
    fields = ["status", "updated_at"]
    if current_period_end is not None:
        sub.current_period_end = current_period_end
        fields.append("current_period_end")
    sub.save(update_fields=fields)
    return sub
