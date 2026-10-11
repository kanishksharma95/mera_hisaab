"""Customer + udhaar views — all tenant-scoped to request.business."""
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render

from core.mixins import business_required

from .forms import ChargeForm, CustomerForm, PaymentForm
from .models import Customer, CustomerLedgerEntry
from .services import record_charge, record_payment

_ZERO = Value(0, output_field=DecimalField(max_digits=14, decimal_places=2))


@business_required
def customer_list(request):
    customers = Customer.objects.for_business(request.business)

    q = request.GET.get("q", "").strip()
    if q:
        customers = customers.filter(Q(name__icontains=q) | Q(phone__icontains=q))

    status = request.GET.get("status", "active")
    if status == "active":
        customers = customers.filter(is_active=True)
    elif status == "inactive":
        customers = customers.filter(is_active=False)

    customers = customers.order_by("name")
    paginator = Paginator(customers, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    querystring = request.GET.copy()
    querystring.pop("page", None)

    return render(
        request,
        "customers/customer_list.html",
        {"page_obj": page_obj, "q": q, "status": status,
         "querystring": querystring.urlencode()},
    )


@business_required
def customer_create(request):
    if request.method == "POST":
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save(commit=False)
            customer.business = request.business
            customer.save()
            messages.success(request, f"Customer '{customer.name}' added.")
            return redirect("customers:detail", pk=customer.pk)
    else:
        form = CustomerForm()
    return render(request, "customers/customer_form.html", {"form": form, "is_edit": False})


@business_required
def customer_edit(request, pk):
    customer = get_object_or_404(Customer, pk=pk, business=request.business)
    if request.method == "POST":
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, "Customer updated.")
            return redirect("customers:detail", pk=customer.pk)
    else:
        form = CustomerForm(instance=customer)
    return render(
        request, "customers/customer_form.html",
        {"form": form, "is_edit": True, "customer": customer},
    )


@business_required
def customer_detail(request, pk):
    customer = get_object_or_404(Customer, pk=pk, business=request.business)
    entries = customer.ledger_entries.all()

    totals = customer.ledger_entries.aggregate(
        total_charged=Coalesce(
            Sum("amount", filter=Q(entry_type=CustomerLedgerEntry.EntryType.DEBIT)), _ZERO
        ),
        total_paid=Coalesce(
            Sum("amount", filter=Q(entry_type=CustomerLedgerEntry.EntryType.CREDIT)), _ZERO
        ),
    )

    return render(
        request,
        "customers/customer_detail.html",
        {
            "customer": customer,
            "entries": entries,
            "totals": totals,
            "payment_form": PaymentForm(),
            "charge_form": ChargeForm(),
            "whatsapp_reminder_url": customer.whatsapp_reminder_url(request.business),
        },
    )



@business_required
def record_payment_view(request, pk):
    customer = get_object_or_404(Customer, pk=pk, business=request.business)
    if request.method == "POST":
        form = PaymentForm(request.POST)
        if form.is_valid():
            record_payment(
                customer=customer,
                amount=form.cleaned_data["amount"],
                method=form.cleaned_data["method"],
                description=form.cleaned_data["description"],
                user=request.user,
            )
            messages.success(request, "Payment recorded.")
            return redirect("customers:detail", pk=customer.pk)
    else:
        form = PaymentForm()
    return render(
        request, "customers/payment_form.html", {"form": form, "customer": customer},
    )


@business_required
def add_udhaar_view(request, pk):
    customer = get_object_or_404(Customer, pk=pk, business=request.business)
    if request.method == "POST":
        form = ChargeForm(request.POST)
        if form.is_valid():
            record_charge(
                customer=customer,
                amount=form.cleaned_data["amount"],
                description=form.cleaned_data["description"],
                due_date=form.cleaned_data["due_date"],
                user=request.user,
            )
            messages.success(request, "Udhaar added.")
            return redirect("customers:detail", pk=customer.pk)
    else:
        form = ChargeForm()
    return render(
        request, "customers/udhaar_form.html", {"form": form, "customer": customer},
    )


@business_required
def udhaar_dashboard(request):
    """Customers with pending udhaar (balance > 0), most-owed first."""
    debtors = (
        Customer.objects.for_business(request.business)
        .filter(is_active=True, current_balance__gt=0)
        .order_by("-current_balance")
    )
    total_outstanding = debtors.aggregate(
        total=Coalesce(Sum("current_balance"), _ZERO)
    )["total"]

    paginator = Paginator(debtors, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "customers/udhaar_dashboard.html",
        {"page_obj": page_obj, "total_outstanding": total_outstanding,
         "debtor_count": debtors.count()},
    )


@business_required
def customer_export_csv(request):
    """Export customers and balances to CSV."""
    import csv
    from django.http import HttpResponse

    customers = (
        Customer.objects.for_business(request.business)
        .order_by("name")
    )
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="customers_export.csv"'
    writer = csv.writer(response)
    writer.writerow([
        "Name",
        "Phone",
        "Email",
        "Address",
        "Current Balance",
        "Credit Limit",
        "Status",
    ])
    for c in customers:
        writer.writerow([
            c.name,
            c.phone,
            c.email,
            c.address,
            c.current_balance,
            c.credit_limit,
            "Active" if c.is_active else "Inactive",
        ])
    return response

