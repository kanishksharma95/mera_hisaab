"""Expense views — an expense log plus dynamic category management.

Tenant-scoped via ``@business_required``; every query goes through
``.for_business(request.business)``.
"""
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render

from core.mixins import business_required

from .forms import ExpenseCategoryForm, ExpenseForm
from .models import Expense, ExpenseCategory
from .services import ensure_default_categories, record_expense

_ZERO = Value(Decimal("0"), output_field=DecimalField(max_digits=14, decimal_places=2))


@business_required
def expense_list(request):
    """List expenses with category/date filters and a period total."""
    ensure_default_categories(request.business)
    expenses = (
        Expense.objects.for_business(request.business)
        .select_related("category", "method")
    )

    category_id = request.GET.get("category", "").strip()
    if category_id.isdigit():
        expenses = expenses.filter(category_id=category_id)

    date_from = request.GET.get("from", "").strip()
    date_to = request.GET.get("to", "").strip()
    if date_from:
        expenses = expenses.filter(spent_on__gte=date_from)
    if date_to:
        expenses = expenses.filter(spent_on__lte=date_to)

    total = expenses.aggregate(t=Coalesce(Sum("amount"), _ZERO))["t"]

    expenses = expenses.order_by("-spent_on", "-created_at")
    paginator = Paginator(expenses, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    querystring = request.GET.copy()
    querystring.pop("page", None)

    return render(request, "expenses/expense_list.html", {
        "page_obj": page_obj,
        "total": total,
        "categories": ExpenseCategory.objects.for_business(request.business).filter(
            is_active=True
        ),
        "category_id": category_id,
        "date_from": date_from,
        "date_to": date_to,
        "querystring": querystring.urlencode(),
    })


@business_required
def expense_create(request):
    ensure_default_categories(request.business)
    if request.method == "POST":
        form = ExpenseForm(request.POST, business=request.business)
        if form.is_valid():
            record_expense(
                business=request.business,
                category=form.cleaned_data["category"],
                amount=form.cleaned_data["amount"],
                method=form.cleaned_data.get("method"),
                spent_on=form.cleaned_data.get("spent_on"),
                note=form.cleaned_data.get("note", ""),
                user=request.user,
            )
            messages.success(request, "Expense recorded.")
            return redirect("expenses:list")
    else:
        form = ExpenseForm(business=request.business)
    return render(request, "expenses/expense_form.html", {"form": form})


# --------------------------------------------------------------------------- #
# Dynamic category management
# --------------------------------------------------------------------------- #
@business_required
def category_list(request):
    ensure_default_categories(request.business)
    categories = ExpenseCategory.objects.for_business(request.business).order_by(
        "sort_order", "name"
    )
    return render(request, "expenses/category_list.html", {"categories": categories})


@business_required
def category_create(request):
    if request.method == "POST":
        form = ExpenseCategoryForm(request.POST, business=request.business)
        if form.is_valid():
            cat = form.save()
            messages.success(request, f"Category '{cat.name}' added.")
            return redirect("expenses:category_list")
    else:
        last = (
            ExpenseCategory.objects.for_business(request.business)
            .order_by("-sort_order")
            .values_list("sort_order", flat=True)
            .first()
        )
        form = ExpenseCategoryForm(
            business=request.business, initial={"sort_order": (last or 0) + 1}
        )
    return render(request, "expenses/category_form.html", {"form": form, "is_edit": False})


@business_required
def category_edit(request, pk):
    cat = get_object_or_404(ExpenseCategory, pk=pk, business=request.business)
    if request.method == "POST":
        form = ExpenseCategoryForm(request.POST, instance=cat, business=request.business)
        if form.is_valid():
            form.save()
            messages.success(request, "Category updated.")
            return redirect("expenses:category_list")
    else:
        form = ExpenseCategoryForm(instance=cat, business=request.business)
    return render(request, "expenses/category_form.html",
                  {"form": form, "is_edit": True, "category": cat})


@business_required
def category_toggle(request, pk):
    cat = get_object_or_404(ExpenseCategory, pk=pk, business=request.business)
    if request.method == "POST":
        cat.is_active = not cat.is_active
        cat.save(update_fields=["is_active", "updated_at"])
        state = "activated" if cat.is_active else "deactivated"
        messages.success(request, f"'{cat.name}' {state}.")
    return redirect("expenses:category_list")


@business_required
def expense_export_csv(request):
    """Export expenses to CSV."""
    import csv
    from django.http import HttpResponse

    expenses = (
        Expense.objects.for_business(request.business)
        .select_related("category", "method")
        .order_by("-spent_on", "-created_at")
    )
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="expenses_export.csv"'
    writer = csv.writer(response)
    writer.writerow(["Date", "Category", "Amount", "Payment Method", "Note"])
    for e in expenses:
        writer.writerow([
            e.spent_on.strftime("%Y-%m-%d"),
            e.category.name if e.category else "",
            e.amount,
            e.method.name if e.method else "",
            e.note,
        ])
    return response

