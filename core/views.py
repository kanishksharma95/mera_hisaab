"""
Core views: landing redirect and the main dashboard.

The Phase 1 dashboard shows real, tenant-scoped values. The cards that depend
on data from later phases (sales, products, udhaar) are computed from the
relevant models when those apps exist; until then they read zero from an empty
tenant rather than showing hardcoded numbers.
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from businesses.models import BusinessMembership
from core.mixins import business_required, role_required


def healthz(request):
    """Additive liveness/readiness probe.

    Checks the DB connection (fatal: returns 503 if down) and does a cache
    round-trip (non-fatal: reported but never fails the probe, so a flaky
    cache can't take the whole service offline). Unauthenticated so platform
    health checks can reach it.
    """
    payload = {"status": "ok"}
    status_code = 200

    # Database — fatal to the probe.
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.fetchone()
        payload["database"] = "connected"
    except Exception as exc:  # pragma: no cover - defensive probe
        payload["status"] = "error"
        payload["database"] = str(exc)
        status_code = 503

    # Cache / Redis — non-fatal; reports which backend is live and whether a
    # set/get round-trip works.
    payload["cache_backend"] = settings.CACHES["default"]["BACKEND"].rsplit(".", 1)[-1]
    try:
        cache.set("healthz", "ok", 10)
        payload["cache"] = "connected" if cache.get("healthz") == "ok" else "unavailable"
    except Exception as exc:  # pragma: no cover - defensive probe
        payload["cache"] = f"error: {exc}"

    return JsonResponse(payload, status=status_code)


@login_required
def home(request):
    """Send logged-in users to their dashboard or onboarding."""
    if request.business is None:
        return redirect("businesses:onboarding")
    return redirect("core:dashboard")


@business_required
def dashboard(request):
    """Main tenant dashboard."""
    business = request.business
    period = request.GET.get("period", "today")
    start, end, label = _resolve_period(period, request)

    # Real, tenant-scoped aggregates. Values from apps not yet built (sales,
    # purchases, expenses, customers) stay 0 until those phases land — never
    # hardcoded. Product/low-stock counts are live as of Phase 2.
    from decimal import Decimal

    from django.db.models import DecimalField, F, Sum, Value
    from django.db.models.functions import Coalesce

    from customers.models import Customer
    from expenses.models import Expense
    from products.models import Product
    from purchases.models import Purchase
    from sales.models import Sale, SaleItem

    active_products = Product.objects.for_business(business).filter(is_active=True)
    active_customers = Customer.objects.for_business(business).filter(is_active=True)

    _zero = Value(Decimal("0"), output_field=DecimalField(max_digits=14, decimal_places=2))

    pending_udhaar = active_customers.filter(current_balance__gt=0).aggregate(
        total=Coalesce(Sum("current_balance"), _zero)
    )["total"]

    # Sales + gross profit for the selected period (real, tenant-scoped).
    period_sales = Sale.objects.for_business(business).filter(
        created_at__gte=start, created_at__lt=end
    )
    sales_agg = period_sales.aggregate(
        revenue=Coalesce(Sum("total"), _zero),
        net_rev=Coalesce(Sum(F("subtotal") - F("order_discount")), _zero),
    )
    cogs = SaleItem.objects.for_business(business).filter(
        sale__created_at__gte=start, sale__created_at__lt=end
    ).aggregate(
        c=Coalesce(Sum(F("cost_price") * F("quantity")), _zero)
    )["c"]
    gross_profit = (sales_agg["net_rev"] or Decimal("0")) - (cogs or Decimal("0"))

    purchases_total = Purchase.objects.for_business(business).filter(
        created_at__gte=start, created_at__lt=end
    ).aggregate(total=Coalesce(Sum("total"), _zero))["total"]

    # Operating expenses for the period (by the date the money was spent).
    # ``end`` may be "now" (same day) or a midnight boundary; subtracting a
    # microsecond gives the correct inclusive last date either way.
    end_date = (end - timedelta(microseconds=1)).date()
    expenses_total = Expense.objects.for_business(business).filter(
        spent_on__gte=start.date(), spent_on__lte=end_date
    ).aggregate(total=Coalesce(Sum("amount"), _zero))["total"]

    # Net profit = gross profit − operating expenses.
    net_profit = gross_profit - (expenses_total or Decimal("0"))

    metrics = {
        "sales_total": sales_agg["revenue"],
        "purchases_total": purchases_total,
        "expenses_total": expenses_total,
        "profit_total": net_profit,
        "total_customers": active_customers.count(),
        "pending_udhaar": pending_udhaar,
        "total_products": active_products.count(),
        "low_stock_count": active_products.filter(
            current_stock__lte=F("min_stock_level")
        ).count(),
    }

    context = {
        "business": business,
        "period": period,
        "period_label": label,
        "period_start": start,
        "period_end": end,
        "period_choices": PERIOD_CHOICES,
        "metrics": metrics,
        "greeting": _greeting(),
    }
    return render(request, "core/dashboard.html", context)


@role_required(
    BusinessMembership.Role.OWNER,
    BusinessMembership.Role.MANAGER,
    BusinessMembership.Role.ACCOUNTANT,
)
def reports(request):
    """Business reports: P&L, sales trend, top products, tax & money position."""

    from decimal import Decimal

    from django.db.models import Count, DecimalField, F, Sum, Value
    from django.db.models.functions import Coalesce, TruncDate, TruncMonth

    from customers.models import Customer
    from expenses.models import Expense
    from purchases.models import Purchase
    from sales.models import Sale, SaleItem
    from suppliers.models import Supplier

    business = request.business
    period = request.GET.get("period", "month")
    start, end, label = _resolve_period(period, request)

    _zero = Value(Decimal("0"), output_field=DecimalField(max_digits=14, decimal_places=2))

    sales = Sale.objects.for_business(business).filter(
        created_at__gte=start, created_at__lt=end
    )
    items = SaleItem.objects.for_business(business).filter(
        sale__created_at__gte=start, sale__created_at__lt=end
    )

    sales_agg = sales.aggregate(
        revenue=Coalesce(Sum("total"), _zero),
        net_rev=Coalesce(Sum(F("subtotal") - F("order_discount")), _zero),
        tax=Coalesce(Sum("tax_total"), _zero),
        count=Count("id"),
    )
    cogs = items.aggregate(c=Coalesce(Sum(F("cost_price") * F("quantity")), _zero))["c"]
    gross_profit = (sales_agg["net_rev"] or Decimal("0")) - (cogs or Decimal("0"))

    end_date = (end - timedelta(microseconds=1)).date()
    expenses_total = Expense.objects.for_business(business).filter(
        spent_on__gte=start.date(), spent_on__lte=end_date
    ).aggregate(t=Coalesce(Sum("amount"), _zero))["t"]
    net_profit = gross_profit - (expenses_total or Decimal("0"))

    purchases_total = Purchase.objects.for_business(business).filter(
        created_at__gte=start, created_at__lt=end
    ).aggregate(t=Coalesce(Sum("total"), _zero))["t"]

    pnl = {
        "revenue": sales_agg["revenue"],
        "net_rev": sales_agg["net_rev"],
        "cogs": cogs,
        "gross_profit": gross_profit,
        "expenses": expenses_total,
        "net_profit": net_profit,
        "tax": sales_agg["tax"],
        "sales_count": sales_agg["count"],
    }

    # Top products by revenue (with quantity), within the period.
    top_products = list(
        items.values("product_name")
        .annotate(
            revenue=Coalesce(Sum("line_total"), _zero),
            qty=Coalesce(Sum("quantity"), Value(Decimal("0"))),
        )
        .order_by("-revenue")[:8]
    )

    # Sales trend: bucket by day for short spans, by month for long ones.
    span_days = (end - start).days
    if span_days > 62:
        buckets = (
            sales.annotate(b=TruncMonth("created_at"))
            .values("b").annotate(total=Coalesce(Sum("total"), _zero)).order_by("b")
        )
        fmt = "%b %Y"
    else:
        buckets = (
            sales.annotate(b=TruncDate("created_at"))
            .values("b").annotate(total=Coalesce(Sum("total"), _zero)).order_by("b")
        )
        fmt = "%d %b"
    trend = [
        {"label": row["b"].strftime(fmt), "total": row["total"]}
        for row in buckets if row["b"]
    ]
    trend_max = max((r["total"] for r in trend), default=Decimal("0")) or Decimal("1")

    # Money position (point-in-time, not period-bound).
    receivables = Customer.objects.for_business(business).filter(
        is_active=True, current_balance__gt=0
    ).aggregate(t=Coalesce(Sum("current_balance"), _zero))["t"]
    payables = Supplier.objects.for_business(business).filter(
        is_active=True, current_balance__gt=0
    ).aggregate(t=Coalesce(Sum("current_balance"), _zero))["t"]

    context = {
        "business": business,
        "period": period,
        "period_label": label,
        "period_start": start,
        "period_end": end,
        "period_choices": PERIOD_CHOICES,
        "pnl": pnl,
        "purchases_total": purchases_total,
        "top_products": top_products,
        "trend": trend,
        "trend_max": trend_max,
        "receivables": receivables,
        "payables": payables,
    }
    return render(request, "core/reports.html", context)


PERIOD_CHOICES = [
    ("today", "Today"),
    ("yesterday", "Yesterday"),
    ("week", "This Week"),
    ("month", "This Month"),
    ("last_month", "Last Month"),
    ("year", "This Year"),
    ("custom", "Custom Range"),
]


def _greeting():
    hour = timezone.localtime().hour
    if hour < 12:
        return "Good Morning"
    if hour < 17:
        return "Good Afternoon"
    return "Good Evening"


def _resolve_period(period, request):
    """Return (start, end, human_label) for a dashboard period filter."""
    now = timezone.localtime()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if period == "yesterday":
        y = today - timedelta(days=1)
        return y, today, "Yesterday"
    if period == "week":
        start = today - timedelta(days=today.weekday())
        return start, now, "This Week"
    if period == "month":
        return today.replace(day=1), now, "This Month"
    if period == "last_month":
        first_this = today.replace(day=1)
        last_month_end = first_this
        last_month_start = (first_this - timedelta(days=1)).replace(day=1)
        return last_month_start, last_month_end, "Last Month"
    if period == "year":
        return today.replace(month=1, day=1), now, "This Year"
    if period == "custom":
        start = _parse_date(request.GET.get("start")) or today
        end = _parse_date(request.GET.get("end")) or now
        return start, end, "Custom Range"
    # default: today
    return today, now, "Today"


def _parse_date(value):
    from django.utils.dateparse import parse_date

    if not value:
        return None
    d = parse_date(value)
    if d is None:
        return None
    return timezone.make_aware(
        timezone.datetime(d.year, d.month, d.day)
    )
