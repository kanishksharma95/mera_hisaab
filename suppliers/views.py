"""Supplier views — tenant-scoped."""
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render

from core.mixins import business_required

from .forms import SupplierForm, SupplierPaymentForm
from .models import Supplier, SupplierLedgerEntry
from .services import record_payment

_ZERO = Value(0, output_field=DecimalField(max_digits=14, decimal_places=2))


@business_required
def supplier_list(request):
    suppliers = Supplier.objects.for_business(request.business)
    q = request.GET.get("q", "").strip()
    if q:
        suppliers = suppliers.filter(Q(name__icontains=q) | Q(phone__icontains=q))
    status = request.GET.get("status", "active")
    if status == "active":
        suppliers = suppliers.filter(is_active=True)
    elif status == "inactive":
        suppliers = suppliers.filter(is_active=False)

    suppliers = suppliers.order_by("name")
    paginator = Paginator(suppliers, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    querystring = request.GET.copy()
    querystring.pop("page", None)
    return render(request, "suppliers/supplier_list.html", {
        "page_obj": page_obj, "q": q, "status": status,
        "querystring": querystring.urlencode(),
    })


@business_required
def supplier_create(request):
    if request.method == "POST":
        form = SupplierForm(request.POST)
        if form.is_valid():
            supplier = form.save(commit=False)
            supplier.business = request.business
            supplier.save()
            messages.success(request, f"Supplier '{supplier.name}' added.")
            return redirect("suppliers:detail", pk=supplier.pk)
    else:
        form = SupplierForm()
    return render(request, "suppliers/supplier_form.html", {"form": form, "is_edit": False})


@business_required
def supplier_edit(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk, business=request.business)
    if request.method == "POST":
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
            messages.success(request, "Supplier updated.")
            return redirect("suppliers:detail", pk=supplier.pk)
    else:
        form = SupplierForm(instance=supplier)
    return render(request, "suppliers/supplier_form.html",
                  {"form": form, "is_edit": True, "supplier": supplier})


@business_required
def supplier_detail(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk, business=request.business)
    entries = supplier.ledger_entries.all()
    totals = supplier.ledger_entries.aggregate(
        total_billed=Coalesce(Sum("amount", filter=Q(entry_type="bill")), _ZERO),
        total_paid=Coalesce(Sum("amount", filter=Q(entry_type="payment")), _ZERO),
    )
    purchases = supplier.purchases.order_by("-created_at")[:10]
    return render(request, "suppliers/supplier_detail.html", {
        "supplier": supplier, "entries": entries, "totals": totals,
        "purchases": purchases, "payment_form": SupplierPaymentForm(),
    })


@business_required
def supplier_payment_view(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk, business=request.business)
    if request.method == "POST":
        form = SupplierPaymentForm(request.POST)
        if form.is_valid():
            record_payment(
                supplier=supplier, amount=form.cleaned_data["amount"],
                method=form.cleaned_data["method"],
                description=form.cleaned_data["description"], user=request.user,
            )
            messages.success(request, "Payment recorded.")
            return redirect("suppliers:detail", pk=supplier.pk)
    else:
        form = SupplierPaymentForm()
    return render(request, "suppliers/supplier_payment_form.html",
                  {"form": form, "supplier": supplier})
