"""
Inventory business logic.

All stock changes go through here so that (a) a transaction is always recorded
and (b) the product's cached ``current_stock`` stays consistent. Uses
``select_for_update`` inside an atomic block to avoid lost updates under
concurrency.
"""
from decimal import Decimal

from django.db import transaction

from products.models import Product

from .models import InventoryTransaction


def record_transaction(*, product, kind, quantity, note="", reference="", user=None):
    """Apply a signed stock delta to ``product`` and log it.

    ``quantity`` is the signed change (positive = stock in, negative = out).
    Returns the created InventoryTransaction. Atomic + row-locked.
    """
    quantity = Decimal(quantity)
    with transaction.atomic():
        locked = Product.objects.select_for_update().get(pk=product.pk)
        new_balance = (locked.current_stock or Decimal("0")) + quantity
        txn = InventoryTransaction.objects.create(
            business=locked.business,
            product=locked,
            kind=kind,
            quantity=quantity,
            balance_after=new_balance,
            note=note,
            reference=reference,
            created_by=user,
        )
        locked.current_stock = new_balance
        locked.save(update_fields=["current_stock", "updated_at"])
        # Keep the caller's in-memory instance in sync too.
        product.current_stock = new_balance
        return txn


def set_opening_stock(*, product, quantity, user=None):
    """Record the initial stock for a newly created product (if any)."""
    quantity = Decimal(quantity)
    if quantity == 0:
        return None
    return record_transaction(
        product=product,
        kind=InventoryTransaction.Kind.OPENING,
        quantity=quantity,
        note="Opening stock",
        user=user,
    )


def adjust_stock(*, product, new_quantity, note="", user=None):
    """Set stock to an absolute ``new_quantity`` via an adjustment transaction.

    Records only the delta needed to reach the target. Returns the transaction,
    or None if there was no change.
    """
    new_quantity = Decimal(new_quantity)
    delta = new_quantity - (product.current_stock or Decimal("0"))
    if delta == 0:
        return None
    return record_transaction(
        product=product,
        kind=InventoryTransaction.Kind.ADJUSTMENT,
        quantity=delta,
        note=note or "Manual stock adjustment",
        user=user,
    )
