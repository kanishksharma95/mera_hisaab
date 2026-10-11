"""Inventory overview, low-stock, and manual stock adjustment."""
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect, render

from core.mixins import business_required
from products.forms import StockAdjustForm
from products.models import Product

from .services import adjust_stock


@business_required
def inventory_list(request):
    products = Product.objects.for_business(request.business).filter(is_active=True)

    q = request.GET.get("q", "").strip()
    if q:
        products = products.filter(Q(name__icontains=q) | Q(sku__icontains=q))

    if request.GET.get("low") == "1":
        products = products.filter(current_stock__lte=F("min_stock_level"))

    products = products.order_by("name")
    paginator = Paginator(products, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    querystring = request.GET.copy()
    querystring.pop("page", None)

    return render(
        request,
        "inventory/inventory_list.html",
        {
            "page_obj": page_obj,
            "q": q,
            "low_only": request.GET.get("low") == "1",
            "querystring": querystring.urlencode(),
        },
    )


@business_required
def stock_adjust(request, product_pk):
    product = get_object_or_404(Product, pk=product_pk, business=request.business)
    if request.method == "POST":
        form = StockAdjustForm(request.POST)
        if form.is_valid():
            txn = adjust_stock(
                product=product,
                new_quantity=form.cleaned_data["new_quantity"],
                note=form.cleaned_data["note"],
                user=request.user,
            )
            if txn is None:
                messages.info(request, "Stock unchanged.")
            else:
                messages.success(
                    request, f"Stock updated to {product.current_stock} {product.unit}."
                )
            return redirect("products:detail", pk=product.pk)
    else:
        form = StockAdjustForm(initial={"new_quantity": product.current_stock})
    return render(
        request,
        "inventory/stock_adjust.html",
        {"form": form, "product": product},
    )
