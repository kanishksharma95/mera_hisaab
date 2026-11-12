"""
Read-only query repository for Mera Hisaab ADK Agent.

Enforces:
1. Every single query is strictly scoped to `business` via `.for_business(business)`.
2. Catalog queries filter `is_active=True`.
3. Read tools return clean Python dictionaries suitable for LLM responses.
"""
from datetime import datetime, time
from decimal import Decimal
from typing import Any, Dict, List, Optional
from django.db.models import F, Q, Sum
from django.utils import timezone

from .context import get_business, require_permission
from .django_setup import init_django


def get_sales_summary(period: str = "today") -> Dict[str, Any]:
    """Return sales summary and totals for the given period ('today', 'week', 'month', 'all')."""
    require_permission("can_view_reports")
    business = get_business()
    init_django()
    from sales.models import Sale

    now = timezone.now()
    qs = Sale.objects.for_business(business)

    if period == "today":
        start_of_day = timezone.make_aware(datetime.combine(now.date(), time.min))
        qs = qs.filter(created_at__gte=start_of_day)
    elif period == "week":
        # last 7 days
        start_of_week = now - timezone.timedelta(days=7)
        qs = qs.filter(created_at__gte=start_of_week)
    elif period == "month":
        # this calendar month
        first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        qs = qs.filter(created_at__gte=first_of_month)

    total_sales_count = qs.count()
    aggregates = qs.aggregate(
        total_revenue=Sum("total"),
        total_paid=Sum("paid_amount"),
        total_due=Sum("due_amount"),
    )

    currency = business.currency_symbol or "₹"
    return {
        "business": business.name,
        "currency": currency,
        "period": period,
        "sales_count": total_sales_count,
        "total_revenue": str(aggregates["total_revenue"] or Decimal("0.00")),
        "total_received": str(aggregates["total_paid"] or Decimal("0.00")),
        "total_udhaar_added": str(aggregates["total_due"] or Decimal("0.00")),
    }


def list_low_stock_products() -> List[Dict[str, Any]]:
    """List products that have stock less than or equal to their min_stock_level."""
    require_permission("can_manage_inventory")
    business = get_business()
    init_django()
    from products.models import Product

    qs = (
        Product.objects.for_business(business)
        .filter(is_active=True, current_stock__lte=F("min_stock_level"))
        .select_related("category")
        .order_by("current_stock")
    )

    results = []
    for p in qs:
        results.append({
            "id": p.id,
            "name": p.name,
            "sku": p.sku,
            "current_stock": str(p.current_stock),
            "min_stock_level": str(p.min_stock_level),
            "unit": p.unit,
            "selling_price": str(p.selling_price),
            "category": p.category.name if p.category else None,
        })
    return results


def search_products(query: str = "", category_id: Optional[int] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """Search active products by name, SKU, or barcode."""
    business = get_business()
    init_django()
    from products.models import Product

    qs = Product.objects.for_business(business).filter(is_active=True).select_related("category")

    if query:
        q = query.strip()
        qs = qs.filter(
            Q(name__icontains=q) | Q(sku__icontains=q) | Q(barcode__icontains=q)
        )

    if category_id:
        qs = qs.filter(category_id=category_id)

    results = []
    for p in qs[:limit]:
        results.append({
            "id": p.id,
            "name": p.name,
            "sku": p.sku,
            "current_stock": str(p.current_stock),
            "unit": p.unit,
            "selling_price": str(p.selling_price),
            "purchase_price": str(p.purchase_price),
            "category": p.category.name if p.category else None,
            "is_low_stock": p.is_low_stock,
        })
    return results


def get_product_detail(product_id_or_sku: str) -> Optional[Dict[str, Any]]:
    """Get full details of a specific active product."""
    business = get_business()
    init_django()
    from products.models import Product

    identifier = str(product_id_or_sku).strip()
    qs = Product.objects.for_business(business).filter(is_active=True)

    product = None
    if identifier.isdigit():
        product = qs.filter(pk=int(identifier)).first()
    if not product:
        product = qs.filter(Q(sku__iexact=identifier) | Q(name__iexact=identifier)).first()

    if not product:
        return None

    return {
        "id": product.id,
        "name": product.name,
        "sku": product.sku,
        "barcode": product.barcode,
        "brand": product.brand,
        "category": product.category.name if product.category else None,
        "unit": product.unit,
        "current_stock": str(product.current_stock),
        "min_stock_level": str(product.min_stock_level),
        "purchase_price": str(product.purchase_price),
        "selling_price": str(product.selling_price),
        "tax_percent": str(product.tax_percent),
        "is_low_stock": product.is_low_stock,
        "stock_value": str(product.stock_value),
    }


def search_customers(query: str = "", limit: int = 20) -> List[Dict[str, Any]]:
    """Search active customers by name or phone number."""
    require_permission("can_manage_customers")
    business = get_business()
    init_django()
    from customers.models import Customer

    qs = Customer.objects.for_business(business).filter(is_active=True)
    if query:
        q = query.strip()
        qs = qs.filter(Q(name__icontains=q) | Q(phone__icontains=q))

    results = []
    for c in qs[:limit]:
        results.append({
            "id": c.id,
            "name": c.name,
            "phone": c.phone,
            "current_balance": str(c.current_balance),
            "has_udhaar": c.has_udhaar,
            "credit_limit": str(c.credit_limit),
        })
    return results


def list_pending_udhaar(limit: int = 20) -> List[Dict[str, Any]]:
    """List all customers who currently owe money to the shop (ordered by highest balance first)."""
    require_permission("can_manage_customers")
    business = get_business()
    init_django()
    from customers.models import Customer

    qs = (
        Customer.objects.for_business(business)
        .filter(is_active=True, current_balance__gt=0)
        .order_by("-current_balance")[:limit]
    )

    results = []
    for c in qs:
        results.append({
            "id": c.id,
            "name": c.name,
            "phone": c.phone,
            "current_balance": str(c.current_balance),
            "whatsapp_reminder_url": c.whatsapp_reminder_url(business),
        })
    return results


def get_customer_detail(customer_id_or_name: str) -> Optional[Dict[str, Any]]:
    """Get full details of a customer including recent ledger transactions."""
    require_permission("can_manage_customers")
    business = get_business()
    init_django()
    from customers.models import Customer

    identifier = str(customer_id_or_name).strip()
    qs = Customer.objects.for_business(business).filter(is_active=True)

    customer = None
    if identifier.isdigit():
        customer = qs.filter(pk=int(identifier)).first()
    if not customer:
        customer = qs.filter(Q(name__iexact=identifier) | Q(phone__iexact=identifier)).first()
    if not customer:
        # Partial match fallback
        customer = qs.filter(name__icontains=identifier).first()

    if not customer:
        return None

    # Get last 5 ledger entries
    ledger = []
    for entry in customer.ledger_entries.order_by("-created_at")[:5]:
        ledger.append({
            "entry_type": entry.entry_type,
            "amount": str(entry.amount),
            "balance_after": str(entry.balance_after),
            "description": entry.description,
            "created_at": entry.created_at.strftime("%Y-%m-%d %H:%M"),
        })

    return {
        "id": customer.id,
        "name": customer.name,
        "phone": customer.phone,
        "email": customer.email,
        "address": customer.address,
        "current_balance": str(customer.current_balance),
        "credit_limit": str(customer.credit_limit),
        "has_udhaar": customer.has_udhaar,
        "whatsapp_reminder_url": customer.whatsapp_reminder_url(business),
        "recent_entries": ledger,
    }


def list_recent_sales(limit: int = 10) -> List[Dict[str, Any]]:
    """List recent invoices/sales for the shop."""
    require_permission("can_access_pos")
    business = get_business()
    init_django()
    from sales.models import Sale

    qs = (
        Sale.objects.for_business(business)
        .select_related("customer")
        .order_by("-created_at")[:limit]
    )

    results = []
    for s in qs:
        results.append({
            "id": s.id,
            "invoice_number": s.invoice_number,
            "total": str(s.total),
            "paid_amount": str(s.paid_amount),
            "due_amount": str(s.due_amount),
            "payment_status": s.payment_status,
            "customer": s.customer.name if s.customer else "Walk-in",
            "created_at": s.created_at.strftime("%Y-%m-%d %H:%M"),
            "is_voided": "[VOIDED]" in (s.notes or ""),
        })
    return results


def get_sale_detail(invoice_number_or_id: str) -> Optional[Dict[str, Any]]:
    """Get full details of a specific invoice including items and payments."""
    require_permission("can_access_pos")
    business = get_business()
    init_django()
    from sales.models import Sale

    identifier = str(invoice_number_or_id).strip()
    qs = Sale.objects.for_business(business)

    sale = None
    if identifier.isdigit():
        sale = qs.filter(pk=int(identifier)).first()
    if not sale:
        sale = qs.filter(invoice_number__iexact=identifier).first()

    if not sale:
        return None

    items = []
    for item in sale.items.all():
        items.append({
            "product_name": item.product_name,
            "quantity": str(item.quantity),
            "unit_price": str(item.unit_price),
            "line_total": str(item.line_total),
        })

    payments = []
    for p in sale.payments.all():
        payments.append({
            "direction": p.direction,
            "method": p.method.name,
            "amount": str(p.amount),
        })

    return {
        "id": sale.id,
        "invoice_number": sale.invoice_number,
        "customer": sale.customer.name if sale.customer else "Walk-in",
        "subtotal": str(sale.subtotal),
        "discount_total": str(sale.discount_total),
        "tax_total": str(sale.tax_total),
        "total": str(sale.total),
        "paid_amount": str(sale.paid_amount),
        "due_amount": str(sale.due_amount),
        "payment_status": sale.payment_status,
        "notes": sale.notes,
        "is_voided": "[VOIDED]" in (sale.notes or ""),
        "created_at": sale.created_at.strftime("%Y-%m-%d %H:%M"),
        "items": items,
        "payments": payments,
    }

