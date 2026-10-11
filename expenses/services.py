"""Expense business logic — dynamic categories + consistent cashbook entries."""
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from payments.models import Payment

from .models import DEFAULT_EXPENSE_CATEGORIES, Expense, ExpenseCategory

_TWOPLACES = Decimal("0.01")


def _money(value):
    return Decimal(str(value)).quantize(_TWOPLACES, rounding=ROUND_HALF_UP)


def ensure_default_categories(business):
    """Create the default expense categories for a business if it has none.

    Called lazily (when the expenses screen loads) so existing businesses get
    categories without a data migration, and everything stays editable.
    """
    if ExpenseCategory.objects.for_business(business).exists():
        return
    for order, name in enumerate(DEFAULT_EXPENSE_CATEGORIES):
        ExpenseCategory.objects.get_or_create(
            business=business, name=name, defaults={"sort_order": order}
        )


@transaction.atomic
def record_expense(*, business, category, amount, method=None, spent_on=None,
                   note="", user=None):
    """Book an expense and mirror it as a money-OUT payment in the cashbook.

    Doing both in one atomic step keeps the expense report and the cashbook in
    agreement — an expense is money that left the drawer.
    """
    amount = _money(amount)
    if amount <= 0:
        raise ValueError("Expense amount must be positive.")
    if category.business_id != business.id:
        raise ValueError("Invalid category for this shop.")
    if method is not None and method.business_id != business.id:
        raise ValueError("Invalid payment method for this shop.")

    fields = dict(
        business=business, category=category, amount=amount, method=method,
        note=note, created_by=user,
    )
    if spent_on:
        fields["spent_on"] = spent_on  # else the model default (today) applies
    expense = Expense.objects.create(**fields)

    if method is not None:
        Payment.objects.create(
            business=business, direction=Payment.Direction.OUT, method=method,
            amount=amount, reference=f"expense:{expense.id}",
            note=note or f"Expense: {category.name}", created_by=user,
        )
    return expense
