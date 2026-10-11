"""Payment views — a cashbook (money in/out) plus payment-method settings.

All views are tenant-scoped via ``@business_required`` and every query goes
through ``.for_business(request.business)`` so a shopkeeper only ever sees
their own money movements.
"""
import json
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.mixins import business_required

from . import gateway
from .forms import PaymentMethodForm
from .models import SAAS_PLANS, BusinessSubscription, Payment, PaymentMethod
from .services import (
    apply_gateway_payment_to_sale,
    ensure_default_methods,
    start_subscription,
    sync_subscription_status,
)

_ZERO = Value(0, output_field=DecimalField(max_digits=14, decimal_places=2))


@business_required
def payment_list(request):
    """Cashbook: every recorded payment, filterable, with in/out totals."""
    payments = (
        Payment.objects.for_business(request.business)
        .select_related("method", "customer", "supplier", "sale", "purchase")
    )

    direction = request.GET.get("direction", "").strip()
    if direction in (Payment.Direction.IN, Payment.Direction.OUT):
        payments = payments.filter(direction=direction)

    method_id = request.GET.get("method", "").strip()
    if method_id.isdigit():
        payments = payments.filter(method_id=method_id)

    # Date range on the payment's creation date (inclusive).
    date_from = request.GET.get("from", "").strip()
    date_to = request.GET.get("to", "").strip()
    if date_from:
        payments = payments.filter(created_at__date__gte=date_from)
    if date_to:
        payments = payments.filter(created_at__date__lte=date_to)

    q = request.GET.get("q", "").strip()
    if q:
        payments = payments.filter(
            Q(reference__icontains=q)
            | Q(note__icontains=q)
            | Q(customer__name__icontains=q)
            | Q(supplier__name__icontains=q)
        )

    totals = payments.aggregate(
        total_in=Coalesce(Sum("amount", filter=Q(direction=Payment.Direction.IN)), _ZERO),
        total_out=Coalesce(Sum("amount", filter=Q(direction=Payment.Direction.OUT)), _ZERO),
    )
    totals["net"] = totals["total_in"] - totals["total_out"]

    payments = payments.order_by("-created_at")
    paginator = Paginator(payments, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    querystring = request.GET.copy()
    querystring.pop("page", None)

    return render(request, "payments/payment_list.html", {
        "page_obj": page_obj,
        "totals": totals,
        "methods": PaymentMethod.objects.for_business(request.business).filter(is_active=True),
        "direction": direction,
        "method_id": method_id,
        "date_from": date_from,
        "date_to": date_to,
        "q": q,
        "querystring": querystring.urlencode(),
    })


@business_required
def method_list(request):
    """Manage the business's payment methods (seeded lazily on first view)."""
    ensure_default_methods(request.business)
    methods = PaymentMethod.objects.for_business(request.business).order_by(
        "sort_order", "name"
    )
    return render(request, "payments/method_list.html", {"methods": methods})


@business_required
def method_create(request):
    if request.method == "POST":
        form = PaymentMethodForm(request.POST, business=request.business)
        if form.is_valid():
            method = form.save()
            messages.success(request, f"Payment method '{method.name}' added.")
            return redirect("payments:method_list")
    else:
        # Default sort_order after the current last one.
        last = (
            PaymentMethod.objects.for_business(request.business)
            .order_by("-sort_order")
            .values_list("sort_order", flat=True)
            .first()
        )
        form = PaymentMethodForm(
            business=request.business, initial={"sort_order": (last or 0) + 1}
        )
    return render(request, "payments/method_form.html", {"form": form, "is_edit": False})


@business_required
def method_edit(request, pk):
    method = get_object_or_404(PaymentMethod, pk=pk, business=request.business)
    if request.method == "POST":
        form = PaymentMethodForm(request.POST, instance=method, business=request.business)
        if form.is_valid():
            form.save()
            messages.success(request, "Payment method updated.")
            return redirect("payments:method_list")
    else:
        form = PaymentMethodForm(instance=method, business=request.business)
    return render(request, "payments/method_form.html",
                  {"form": form, "is_edit": True, "method": method})


@business_required
def method_toggle(request, pk):
    """Activate / deactivate a method (soft — history is preserved)."""
    method = get_object_or_404(PaymentMethod, pk=pk, business=request.business)
    if request.method == "POST":
        method.is_active = not method.is_active
        method.save(update_fields=["is_active", "updated_at"])
        state = "activated" if method.is_active else "deactivated"
        messages.success(request, f"'{method.name}' {state}.")
    return redirect("payments:method_list")


# --------------------------------------------------------------------------- #
# Customer invoice collection (public — reachable via the shareable link)
# --------------------------------------------------------------------------- #
def _get_public_sale(token):
    from sales.models import Sale

    return get_object_or_404(
        Sale.objects.select_related("business", "customer"), public_token=token
    )


@require_POST
def create_invoice_order(request, token):
    """Create a Razorpay order for a sale's outstanding amount.

    Public: the customer opening the shared invoice link triggers this. Returns
    the JSON that Checkout needs (never the secret key).
    """
    if not gateway.is_configured():
        return JsonResponse({"error": "Online payments are not enabled."}, status=503)

    sale = _get_public_sale(token)
    if sale.due_amount <= 0:
        return JsonResponse({"error": "This invoice is already paid."}, status=400)

    order = gateway.create_order(
        amount=sale.due_amount,
        receipt=f"sale:{sale.id}",
        notes={"sale_id": str(sale.id), "business_id": str(sale.business_id)},
    )
    return JsonResponse({
        "key_id": settings.RAZORPAY_KEY_ID,
        "order_id": order["id"],
        "amount": order["amount"],
        "currency": order["currency"],
        "name": sale.business.name,
        "description": f"Invoice {sale.invoice_number}",
        "prefill": {
            "name": sale.customer.name if sale.customer else "",
            "contact": sale.customer.phone if sale.customer else "",
        },
    })


@require_POST
def invoice_payment_callback(request, token):
    """Browser callback after Checkout succeeds. Verifies + records the payment.

    The webhook is the ultimate source of truth; this handler just gives the
    customer instant confirmation. Both paths are idempotent.
    """
    sale = _get_public_sale(token)
    order_id = request.POST.get("razorpay_order_id", "")
    payment_id = request.POST.get("razorpay_payment_id", "")
    signature = request.POST.get("razorpay_signature", "")

    try:
        gateway.verify_payment_signature(
            order_id=order_id, payment_id=payment_id, signature=signature
        )
    except Exception:
        messages.error(request, "Payment could not be verified. Please contact the shop.")
        return redirect("public_invoice", token=token)

    apply_gateway_payment_to_sale(
        sale=sale, razorpay_payment_id=payment_id, razorpay_order_id=order_id
    )
    messages.success(request, "Payment successful. Thank you!")
    return redirect("public_invoice", token=token)


# --------------------------------------------------------------------------- #
# Webhook (source of truth for BOTH invoice payments and subscriptions)
# --------------------------------------------------------------------------- #
@csrf_exempt
@require_POST
def razorpay_webhook(request):
    """Receive and verify Razorpay webhooks, then update local state.

    Signature verification is mandatory — without it anyone could POST a fake
    'paid' event. Unknown events are acknowledged (200) but ignored.
    """
    signature = request.headers.get("X-Razorpay-Signature", "")
    try:
        gateway.verify_webhook_signature(body=request.body, signature=signature)
    except Exception:
        return HttpResponseBadRequest("Invalid signature")

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return HttpResponseBadRequest("Invalid payload")

    event = payload.get("event", "")

    if event in ("payment.captured", "order.paid"):
        _handle_payment_event(payload)
    elif event.startswith("subscription."):
        _handle_subscription_event(payload)

    # Always 200 for events we understood or chose to ignore, so Razorpay
    # stops retrying.
    return HttpResponse(status=200)


def _handle_payment_event(payload):
    from sales.models import Sale

    entity = (
        payload.get("payload", {}).get("payment", {}).get("entity", {})
    )
    notes = entity.get("notes") or {}
    sale_id = notes.get("sale_id")
    payment_id = entity.get("id")
    if not (sale_id and payment_id):
        return
    sale = Sale.objects.filter(pk=sale_id).select_related("customer").first()
    if sale is None:
        return
    apply_gateway_payment_to_sale(
        sale=sale,
        razorpay_payment_id=payment_id,
        razorpay_order_id=entity.get("order_id", ""),
        amount=(entity.get("amount", 0) or 0) / 100,  # paise -> rupees
    )


def _handle_subscription_event(payload):
    entity = (
        payload.get("payload", {}).get("subscription", {}).get("entity", {})
    )
    sub_id = entity.get("id")
    status = entity.get("status")
    if not (sub_id and status):
        return
    period_end = entity.get("current_end")
    end_dt = (
        datetime.fromtimestamp(period_end, tz=dt_timezone.utc) if period_end else None
    )
    sync_subscription_status(
        razorpay_subscription_id=sub_id, status=status, current_period_end=end_dt
    )


# --------------------------------------------------------------------------- #
# SaaS subscription billing (shopkeeper-facing)
# --------------------------------------------------------------------------- #
@business_required
def billing(request):
    """Show the business's current plan/subscription and available plans."""
    subscription = getattr(request.business, "subscription", None)
    plans = [{"code": code, **spec} for code, spec in SAAS_PLANS.items()]
    return render(request, "payments/billing.html", {
        "subscription": subscription,
        "plans": plans,
        "gateway_ready": gateway.is_configured(),
    })


@business_required
@require_POST
def create_subscription_view(request):
    """Start a Razorpay subscription for the chosen plan."""
    if not gateway.is_configured():
        messages.error(request, "Online billing is not enabled yet.")
        return redirect("payments:billing")

    plan_code = request.POST.get("plan_code", "")
    if plan_code not in SAAS_PLANS:
        messages.error(request, "Please choose a valid plan.")
        return redirect("payments:billing")

    try:
        _, rzp_sub = start_subscription(
            business=request.business, plan_code=plan_code, user=request.user
        )
    except Exception:
        messages.error(request, "Could not start the subscription. Please try again.")
        return redirect("payments:billing")

    # Razorpay returns a hosted checkout URL for subscriptions.
    short_url = rzp_sub.get("short_url")
    if short_url:
        return redirect(short_url)
    messages.success(request, "Subscription created.")
    return redirect("payments:billing")
