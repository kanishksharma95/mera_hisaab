"""
Purchases: a stock-in document (supplier bill) and its line items.

Completing a purchase (see ``purchases.services.create_purchase``) atomically:
  * generates an internal purchase number,
  * increases stock via the EXISTING inventory service,
  * updates each product's latest purchase cost (keeps COGS current),
  * posts the bill + any payment to the EXISTING supplier ledger.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import TenantBaseModel


class Purchase(TenantBaseModel):
    class PaymentStatus(models.TextChoices):
        PAID = "paid", _("Paid")
        PARTIAL = "partial", _("Partially paid")
        UNPAID = "unpaid", _("Unpaid")

    number = models.CharField(max_length=30, db_index=True)
    number_seq = models.PositiveIntegerField(default=0)
    # The supplier's own bill/invoice number (free text, optional).
    supplier_invoice = models.CharField(max_length=60, blank=True)

    supplier = models.ForeignKey(
        "suppliers.Supplier", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="purchases",
    )

    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    order_discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    paid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    due_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    payment_status = models.CharField(
        max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.PAID
    )

    notes = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="purchases_created",
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["business", "-created_at"]),
            models.Index(fields=["business", "number"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "number"], name="unique_purchase_number_per_business"
            )
        ]

    def __str__(self):
        return self.number


class PurchaseItem(TenantBaseModel):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "products.Product", on_delete=models.SET_NULL, null=True, related_name="purchase_items"
    )
    product_name = models.CharField(max_length=200)

    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2)
    discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ("id",)

    def __str__(self):
        return f"{self.product_name} × {self.quantity}"
