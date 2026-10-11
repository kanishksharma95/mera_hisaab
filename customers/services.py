"""
Customer ledger business logic.

All balance changes go through ``post_entry`` (atomic + row-locked) so the
ledger and ``Customer.current_balance`` never drift apart. Sales in Phase 4
will call ``record_charge`` for credit sales; ``record_payment`` is used when a
customer pays down their udhaar.
"""
from decimal import Decimal

from django.db import transaction

from .models import Customer, CustomerLedgerEntry


def post_entry(
    *, customer, entry_type, amount, description="", reference="",
    method="", due_date=None, user=None,
):
    """Append a ledger entry and update the customer's running balance.

    ``amount`` must be positive; direction is decided by ``entry_type``.
    Returns the created CustomerLedgerEntry.
    """
    amount = Decimal(amount)
    if amount <= 0:
        raise ValueError("Ledger amount must be positive.")

    with transaction.atomic():
        locked = Customer.objects.select_for_update().get(pk=customer.pk)
        if entry_type == CustomerLedgerEntry.EntryType.DEBIT:
            new_balance = locked.current_balance + amount
        else:
            new_balance = locked.current_balance - amount

        entry = CustomerLedgerEntry.objects.create(
            business=locked.business,
            customer=locked,
            entry_type=entry_type,
            amount=amount,
            balance_after=new_balance,
            description=description,
            reference=reference,
            method=method,
            due_date=due_date,
            created_by=user,
        )
        locked.current_balance = new_balance
        locked.save(update_fields=["current_balance", "updated_at"])
        customer.current_balance = new_balance
        return entry


def record_charge(*, customer, amount, description="", reference="", due_date=None, user=None):
    """Increase udhaar (customer owes more) — e.g. a credit sale or manual charge."""
    return post_entry(
        customer=customer,
        entry_type=CustomerLedgerEntry.EntryType.DEBIT,
        amount=amount,
        description=description or "Udhaar",
        reference=reference,
        due_date=due_date,
        user=user,
    )


def record_payment(*, customer, amount, description="", method="", reference="", user=None):
    """Decrease udhaar — a payment received from the customer."""
    return post_entry(
        customer=customer,
        entry_type=CustomerLedgerEntry.EntryType.CREDIT,
        amount=amount,
        description=description or "Payment received",
        reference=reference,
        method=method,
        user=user,
    )
