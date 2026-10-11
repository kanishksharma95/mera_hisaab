"""
Suppliers and their payable ledger.

Mirrors the customer/udhaar design, with the sign flipped in meaning:
  * ``Supplier.current_balance`` positive => the shop OWES the supplier
    (accounts payable);
  * a BILL entry (a credit purchase) increases the payable;
  * a PAYMENT entry (money paid to the supplier) decreases it.

All balance changes go through ``suppliers.services`` (atomic + row-locked).
"""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import SoftDeleteModel, TenantBaseModel


class Supplier(TenantBaseModel, SoftDeleteModel):
    name = models.CharField(max_length=150, db_index=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    gst_number = models.CharField(_("GST number"), max_length=20, blank=True)
    notes = models.TextField(blank=True)

    # Positive => amount payable (shop owes the supplier).
    current_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ("name",)
        indexes = [
            models.Index(fields=["business", "name"]),
            models.Index(fields=["business", "phone"]),
        ]

    def __str__(self):
        return self.name

    @property
    def has_payable(self):
        return self.current_balance > 0


class SupplierLedgerEntry(TenantBaseModel):
    """An immutable accounting line for a supplier."""

    class EntryType(models.TextChoices):
        BILL = "bill", _("Bill (purchase on credit)")
        PAYMENT = "payment", _("Payment made")

    supplier = models.ForeignKey(
        Supplier, on_delete=models.CASCADE, related_name="ledger_entries"
    )
    entry_type = models.CharField(max_length=10, choices=EntryType.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)

    description = models.CharField(max_length=255, blank=True)
    method = models.CharField(max_length=40, blank=True)
    reference = models.CharField(max_length=60, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="supplier_ledger_entries",
    )

    class Meta:
        verbose_name_plural = "supplier ledger entries"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["business", "supplier", "-created_at"])]

    def __str__(self):
        return f"{self.supplier.name} {self.entry_type} {self.amount}"
