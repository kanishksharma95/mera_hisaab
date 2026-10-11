"""SaaS plan quotas and feature limits for Mera Hisaab.

Enforces Free vs Pro subscription tier boundaries.
"""
from django.utils import timezone

FREE_TIER_LIMITS = {
    "max_products": 50,
    "max_staff": 1,
    "max_monthly_sales": 100,
}


def is_pro_business(business):
    """Return True if the business has an active Pro SaaS subscription."""
    sub = getattr(business, "subscription", None)
    return bool(sub and sub.is_active)


def can_add_product(business):
    """Check if business can add more products."""
    if is_pro_business(business):
        return True, ""

    from products.models import Product

    current_count = Product.objects.for_business(business).count()
    limit = FREE_TIER_LIMITS["max_products"]
    if current_count >= limit:
        return (
            False,
            f"Free plan limit reached ({limit} products). Please upgrade to Pro for unlimited products.",
        )
    return True, ""


def can_add_staff(business):
    """Check if business can add more team members."""
    if is_pro_business(business):
        return True, ""

    from businesses.models import BusinessMembership

    current_count = BusinessMembership.objects.for_business(business).filter(is_active=True).count()
    limit = FREE_TIER_LIMITS["max_staff"]
    if current_count >= limit:
        return (
            False,
            f"Free plan allows only {limit} user. Upgrade to Pro to add cashiers, managers, and accountants.",
        )
    return True, ""


def can_create_sale(business):
    """Check if business can record more sales this calendar month."""
    if is_pro_business(business):
        return True, ""

    from sales.models import Sale

    now = timezone.localtime()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_sales_count = (
        Sale.objects.for_business(business)
        .filter(created_at__gte=start_of_month)
        .count()
    )
    limit = FREE_TIER_LIMITS["max_monthly_sales"]
    if month_sales_count >= limit:
        return (
            False,
            f"Free plan limit of {limit} sales this month reached. Upgrade to Pro for unlimited billing.",
        )
    return True, ""
