"""
Sales: a completed sale (the invoice) and its line items.

The Sale row IS the invoice — it carries the unique invoice number and the
server-computed totals. We deliberately do NOT keep a separate near-duplicate
Invoice table (the invoice is a rendered view of a Sale, incl. a public,
tokenised page for WhatsApp sharing).

Every money field is computed on the backend by ``sales.services.create_sale``;
nothing here trusts client-side arithmetic. Line items snapshot the cost price
at sale time so Cost of Goods Sold / profit stay correct even if the product's
price changes later.
"""
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import TenantBaseModel


class Sale(TenantBaseModel):
    class PaymentStatus(models.TextChoices):
        PAID = "paid", _("Paid")
        PARTIAL = "partial", _("Partially paid")
        UNPAID = "unpaid", _("Unpaid")

    invoice_number = models.CharField(max_length=30, db_index=True)
    invoice_seq = models.PositiveIntegerField(default=0)
    # Public, unguessable token for the shareable invoice page (WhatsApp).
    public_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sales",
    )

    # subtotal is net-of-tax and already has per-line discounts removed.
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    # discount_total = per-line discounts + order_discount (for display).
    discount_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    # order-level discount only (kept separate so profit maths stays correct).
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
        related_name="sales_created",
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["business", "-created_at"]),
            models.Index(fields=["business", "invoice_number"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "invoice_number"],
                name="unique_invoice_number_per_business",
            )
        ]

    def __str__(self):
        return self.invoice_number

    @property
    def cost_total(self):
        """Cost of goods sold for this sale (from snapshotted item costs)."""
        return sum((i.cost_total for i in self.items.all()), Decimal("0.00"))

    @property
    def gross_profit(self):
        """Net revenue (excl. tax, after all discounts) minus COGS.

        ``subtotal`` already excludes per-line discounts, so only the
        order-level discount is subtracted here (avoids double-counting).
        """
        return (self.subtotal - self.order_discount) - self.cost_total


class SaleItem(TenantBaseModel):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "products.Product", on_delete=models.SET_NULL, null=True, related_name="sale_items"
    )
    # Snapshot of product name so historical invoices stay readable.
    product_name = models.CharField(max_length=200)

    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    cost_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ("id",)

    def __str__(self):
        return f"{self.product_name} × {self.quantity}"

    @property
    def cost_total(self):
        return (self.cost_price * self.quantity).quantize(Decimal("0.01"))
