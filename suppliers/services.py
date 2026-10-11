"""Supplier ledger business logic (atomic + row-locked)."""
from decimal import Decimal

from django.db import transaction

from .models import Supplier, SupplierLedgerEntry


def post_entry(*, supplier, entry_type, amount, description="", reference="",
               method="", user=None):
    """Append a ledger entry and update the supplier's payable balance."""
    amount = Decimal(amount)
    if amount <= 0:
        raise ValueError("Ledger amount must be positive.")

    with transaction.atomic():
        locked = Supplier.objects.select_for_update().get(pk=supplier.pk)
        if entry_type == SupplierLedgerEntry.EntryType.BILL:
            new_balance = locked.current_balance + amount   # we owe more
        else:
            new_balance = locked.current_balance - amount   # we paid, owe less

        entry = SupplierLedgerEntry.objects.create(
            business=locked.business, supplier=locked, entry_type=entry_type,
            amount=amount, balance_after=new_balance, description=description,
            reference=reference, method=method, created_by=user,
        )
        locked.current_balance = new_balance
        locked.save(update_fields=["current_balance", "updated_at"])
        supplier.current_balance = new_balance
        return entry


def record_bill(*, supplier, amount, description="", reference="", user=None):
    """Increase payable — a purchase billed on credit."""
    return post_entry(
        supplier=supplier, entry_type=SupplierLedgerEntry.EntryType.BILL,
        amount=amount, description=description or "Purchase bill",
        reference=reference, user=user,
    )


def record_payment(*, supplier, amount, description="", method="", reference="", user=None):
    """Decrease payable — money paid to the supplier."""
    return post_entry(
        supplier=supplier, entry_type=SupplierLedgerEntry.EntryType.PAYMENT,
        amount=amount, description=description or "Payment made",
        reference=reference, method=method, user=user,
    )
