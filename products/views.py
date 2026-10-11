"""Product and category views — all tenant-scoped to request.business."""
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.mixins import business_required
from inventory.services import set_opening_stock

from .forms import CategoryForm, ProductForm
from .models import Product, ProductCategory

SORT_FIELDS = {
    "name": "name",
    "-name": "-name",
    "price": "selling_price",
    "-price": "-selling_price",
    "stock": "current_stock",
    "-stock": "-current_stock",
    "newest": "-created_at",
}


# --------------------------------------------------------------------------- #
# Products
# --------------------------------------------------------------------------- #
@business_required
def product_list(request):
    products = (
        Product.objects.for_business(request.business)
        .select_related("category")
    )

    q = request.GET.get("q", "").strip()
    if q:
        products = products.filter(
            Q(name__icontains=q) | Q(sku__icontains=q) | Q(barcode__icontains=q)
            | Q(brand__icontains=q)
        )

    category_id = request.GET.get("category")
    if category_id:
        products = products.filter(category_id=category_id)

    status = request.GET.get("status", "active")
    if status == "active":
        products = products.filter(is_active=True)
    elif status == "inactive":
        products = products.filter(is_active=False)

    sort = request.GET.get("sort", "name")
    products = products.order_by(SORT_FIELDS.get(sort, "name"))

    paginator = Paginator(products, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    querystring = request.GET.copy()
    querystring.pop("page", None)

    context = {
        "page_obj": page_obj,
        "categories": ProductCategory.objects.for_business(request.business).filter(
            is_active=True
        ),
        "q": q,
        "status": status,
        "sort": sort,
        "selected_category": category_id,
        "querystring": querystring.urlencode(),
    }
    return render(request, "products/product_list.html", context)


@business_required
def product_create(request):
    from payments.limits import can_add_product

    allowed, limit_msg = can_add_product(request.business)
    if not allowed:
        messages.warning(request, limit_msg)
        return redirect("payments:billing")

    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES, business=request.business)
        if form.is_valid():
            with transaction.atomic():
                product = form.save(commit=False)
                product.business = request.business
                product.save()
                form.save_attributes(product)
                opening = form.cleaned_data.get("opening_stock") or 0
                set_opening_stock(
                    product=product, quantity=opening, user=request.user
                )
            messages.success(request, f"Product '{product.name}' added.")
            return redirect("products:detail", pk=product.pk)
    else:
        form = ProductForm(business=request.business)

    return render(
        request, "products/product_form.html", {"form": form, "is_edit": False}
    )


@business_required
def product_edit(request, pk):
    product = get_object_or_404(
        Product, pk=pk, business=request.business
    )
    if request.method == "POST":
        form = ProductForm(
            request.POST, request.FILES, instance=product, business=request.business
        )
        if form.is_valid():
            with transaction.atomic():
                product = form.save()
                form.save_attributes(product)
            messages.success(request, "Product updated.")
            return redirect("products:detail", pk=product.pk)
    else:
        form = ProductForm(instance=product, business=request.business)
    return render(
        request,
        "products/product_form.html",
        {"form": form, "is_edit": True, "product": product},
    )


@business_required
def product_detail(request, pk):
    product = get_object_or_404(
        Product.objects.select_related("category"),
        pk=pk,
        business=request.business,
    )
    attributes = product.attributes.select_related("field").all()
    transactions = product.inventory_transactions.all()[:20]
    return render(
        request,
        "products/product_detail.html",
        {"product": product, "attributes": attributes, "transactions": transactions},
    )


@business_required
@require_POST
def product_toggle(request, pk):
    product = get_object_or_404(Product, pk=pk, business=request.business)
    product.is_active = not product.is_active
    product.save(update_fields=["is_active", "updated_at"])
    state = "activated" if product.is_active else "deactivated"
    messages.info(request, f"Product {state}.")
    return redirect(request.POST.get("next") or reverse("products:list"))


# --------------------------------------------------------------------------- #
# Categories
# --------------------------------------------------------------------------- #
@business_required
def category_list(request):
    categories = ProductCategory.objects.for_business(request.business).order_by(
        "-is_active", "name"
    )
    return render(
        request, "products/category_list.html", {"categories": categories}
    )


@business_required
def category_create(request):
    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.business = request.business
            category.save()
            messages.success(request, f"Category '{category.name}' added.")
            return redirect("products:category_list")
    else:
        form = CategoryForm()
    return render(
        request, "products/category_form.html", {"form": form, "is_edit": False}
    )


@business_required
def category_edit(request, pk):
    category = get_object_or_404(ProductCategory, pk=pk, business=request.business)
    if request.method == "POST":
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, "Category updated.")
            return redirect("products:category_list")
    else:
        form = CategoryForm(instance=category)
    return render(
        request,
        "products/category_form.html",
        {"form": form, "is_edit": True, "category": category},
    )


@business_required
@require_POST
def category_toggle(request, pk):
    category = get_object_or_404(ProductCategory, pk=pk, business=request.business)
    category.is_active = not category.is_active
    category.save(update_fields=["is_active", "updated_at"])
    messages.info(request, "Category updated.")
    return redirect("products:category_list")
