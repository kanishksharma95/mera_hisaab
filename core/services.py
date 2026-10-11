"""Shared, cross-app services."""
from django.db import transaction

from .models import NumberSequence


def next_number(*, business, key, year, prefix="MH", width=6):
    """Return the next formatted document number for a business, e.g. MH-2026-000001.

    Atomically increments a per-(business, key, year) counter using
    ``select_for_update`` so concurrent sales can never collide or reuse a
    number. Must be called inside an outer transaction (the billing service
    provides one).
    """
    seq, _ = NumberSequence.objects.select_for_update().get_or_create(
        business=business, key=key, year=year
    )
    seq.last_value += 1
    seq.save(update_fields=["last_value"])
    return f"{prefix}-{year}-{seq.last_value:0{width}d}", seq.last_value
