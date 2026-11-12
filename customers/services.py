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


def create_customer(
    *,
    business,
    name,
    phone="",
    email="",
    address="",
    credit_limit=0,
    notes="",
    user=None,
):
    """Create a new customer profile.
    
    Balance starts at 0 and changes only via ledger entries (post_entry/record_charge).
    """
    from django.core.exceptions import ValidationError

    name = (name or "").strip()
    if not name:
        raise ValidationError("Customer name is required.")

    credit_limit = Decimal(str(credit_limit or 0))
    if credit_limit < 0:
        raise ValidationError("Credit limit cannot be negative.")

    return Customer.objects.create(
        business=business,
        name=name,
        phone=(phone or "").strip(),
        email=(email or "").strip(),
        address=(address or "").strip(),
        credit_limit=credit_limit,
        notes=(notes or "").strip(),
    )


def update_customer(
    *,
    customer,
    name=None,
    phone=None,
    email=None,
    address=None,
    credit_limit=None,
    notes=None,
    user=None,
):
    """Update non-ledger fields of a customer profile.
    
    current_balance is never modified directly.
    """
    from django.core.exceptions import ValidationError

    update_fields = ["updated_at"]

    if name is not None:
        name = name.strip()
        if not name:
            raise ValidationError("Customer name cannot be empty.")
        customer.name = name
        update_fields.append("name")

    if phone is not None:
        customer.phone = phone.strip()
        update_fields.append("phone")

    if email is not None:
        customer.email = email.strip()
        update_fields.append("email")

    if address is not None:
        customer.address = address.strip()
        update_fields.append("address")

    if credit_limit is not None:
        cl = Decimal(str(credit_limit))
        if cl < 0:
            raise ValidationError("Credit limit cannot be negative.")
        customer.credit_limit = cl
        update_fields.append("credit_limit")

    if notes is not None:
        customer.notes = notes.strip()
        update_fields.append("notes")

    customer.save(update_fields=update_fields)
    return customer


def deactivate_customer(*, customer, user=None):
    """Soft-delete a customer."""
    customer.deactivate()
    return customer

