"""
Inventory ledger.

Every stock movement is an immutable ``InventoryTransaction`` row. Stock is
never changed without one, so a product's stock is always reconstructable by
summing its transactions — a proper audit trail.
"""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import TenantBaseModel


class InventoryTransaction(TenantBaseModel):
    """A single, signed change to a product's stock."""

    class Kind(models.TextChoices):
        OPENING = "opening", _("Opening stock")
        PURCHASE = "purchase", _("Purchase")
        SALE = "sale", _("Sale")
        RETURN = "return", _("Return")
        ADJUSTMENT = "adjustment", _("Adjustment")

    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="inventory_transactions",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    # Signed delta: positive increases stock, negative decreases it.
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    # Stock balance immediately after this transaction (for fast auditing).
    balance_after = models.DecimalField(max_digits=12, decimal_places=3)
    note = models.CharField(max_length=255, blank=True)

    # Loose reference to the source document (e.g. "sale:42"), populated by
    # later phases. Kept generic to avoid coupling inventory to those apps.
    reference = models.CharField(max_length=60, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_transactions",
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["business", "product", "-created_at"]),
        ]

    def __str__(self):
        sign = "+" if self.quantity >= 0 else ""
        return f"{self.product.name} {sign}{self.quantity} ({self.get_kind_display()})"
