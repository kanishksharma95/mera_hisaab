"""Purchase views — entry (stock-in), list, detail. Tenant-scoped."""
import json

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from core.mixins import business_required
from payments.models import PaymentMethod
from payments.services import ensure_default_methods
from products.models import Product
from suppliers.models import Supplier

from .models import Purchase
from .services import create_purchase


@business_required
def purchase_create(request):
    ensure_default_methods(request.business)
    return render(request, "purchases/purchase_form.html", {
        "suppliers": Supplier.objects.for_business(request.business).filter(is_active=True).order_by("name"),
        "payment_methods": PaymentMethod.objects.for_business(request.business).filter(is_active=True),
        "currency_symbol": request.business.currency_symbol,
    })


@business_required
@require_GET
def purchase_search(request):
    q = request.GET.get("q", "").strip()
    products = Product.objects.for_business(request.business).filter(is_active=True)
    if q:
        products = products.filter(
            Q(name__icontains=q) | Q(sku__icontains=q) | Q(barcode__icontains=q)
        )
    products = products.order_by("name")[:24]
    data = [{
        "id": p.id, "name": p.name, "cost": str(p.purchase_price),
        "tax": str(p.tax_percent), "unit": p.unit, "stock": str(p.current_stock),
    } for p in products]
    return JsonResponse({"results": data})


@business_required
@require_POST
def purchase_checkout(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid request."}, status=400)

    items = [{
        "product": it.get("product"), "quantity": it.get("quantity"),
        "unit_cost": it.get("unit_cost"), "discount": it.get("discount", 0),
    } for it in (payload.get("items") or [])]
    payments = [{"method": p.get("method"), "amount": p.get("amount")}
                for p in (payload.get("payments") or [])]

    supplier = None
    supplier_id = payload.get("supplier")
    if supplier_id:
        supplier = Supplier.objects.for_business(request.business).filter(pk=supplier_id).first()
        if supplier is None:
            return JsonResponse({"error": "Invalid supplier."}, status=400)

    try:
        purchase = create_purchase(
            business=request.business, user=request.user, items=items,
            supplier=supplier, order_discount=payload.get("order_discount", 0) or 0,
            payments=payments, supplier_invoice=payload.get("supplier_invoice", "") or "",
            notes=payload.get("notes", "") or "",
        )
    except ValidationError as exc:
        return JsonResponse({"error": "; ".join(exc.messages)}, status=400)
    except (TypeError, ValueError, KeyError):
        return JsonResponse({"error": "Could not process the purchase. Please check the items."}, status=400)

    return JsonResponse({"ok": True, "number": purchase.number,
                         "redirect": reverse("purchases:detail", args=[purchase.pk])})


@business_required
def purchase_list(request):
    purchases = Purchase.objects.for_business(request.business).select_related("supplier")
    q = request.GET.get("q", "").strip()
    if q:
        purchases = purchases.filter(
            Q(number__icontains=q) | Q(supplier__name__icontains=q) | Q(supplier_invoice__icontains=q)
        )
    status = request.GET.get("status")
    if status in {"paid", "partial", "unpaid"}:
        purchases = purchases.filter(payment_status=status)

    purchases = purchases.order_by("-created_at")
    paginator = Paginator(purchases, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    querystring = request.GET.copy()
    querystring.pop("page", None)
    return render(request, "purchases/purchase_list.html", {
        "page_obj": page_obj, "q": q, "status": status,
        "querystring": querystring.urlencode(),
    })


@business_required
def purchase_detail(request, pk):
    purchase = get_object_or_404(
        Purchase.objects.select_related("supplier").prefetch_related("items", "payments__method"),
        pk=pk, business=request.business,
    )
    return render(request, "purchases/purchase_detail.html", {"purchase": purchase})
