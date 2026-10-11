"""
Customers and their udhaar (credit) ledger.

Balance convention:
  * A DEBIT increases what the customer owes the shop (a credit sale / udhaar
    given, or a manual charge).
  * A CREDIT decreases it (a payment received from the customer).
  * ``Customer.current_balance`` is the running balance: positive => customer
    owes the shop (pending udhaar); negative => the shop holds an advance.

Every change goes through ``customers.services`` so a ledger row is always
written and ``current_balance`` stays consistent (same discipline as inventory).
"""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import SoftDeleteModel, TenantBaseModel


class Customer(TenantBaseModel, SoftDeleteModel):
    name = models.CharField(max_length=150, db_index=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    # Running udhaar balance (positive => customer owes the shop).
    current_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    # 0 means "no limit". Used to warn when extending further credit.
    credit_limit = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ("name",)
        indexes = [
            models.Index(fields=["business", "name"]),
            models.Index(fields=["business", "phone"]),
        ]

    def __str__(self):
        return self.name

    @property
    def has_udhaar(self):
        return self.current_balance > 0

    @property
    def is_advance(self):
        return self.current_balance < 0

    def whatsapp_reminder_url(self, business=None):
        """Build free wa.me URL to send udhaar payment reminder directly."""
        from urllib.parse import quote

        phone = ""
        if self.phone:
            digits = "".join(ch for ch in self.phone if ch.isdigit())
            if len(digits) == 10:
                digits = "91" + digits
            phone = digits

        biz = business or getattr(self, "business", None)
        sym = biz.currency_symbol if biz else "₹"
        shop_name = biz.name if biz else "Our Shop"
        lines = [
            f"Namaste {self.name},",
            f"This is a gentle payment reminder from {shop_name}.",
            f"Your pending udhaar balance is: {sym}{self.current_balance}.",
            "Please clear this pending balance when convenient.",
            "",
            "Thank you!",
            "Powered by Mera Hisaab",
        ]
        text = quote("\n".join(lines))
        return f"https://wa.me/{phone}?text={text}"



class CustomerLedgerEntry(TenantBaseModel):
    """An immutable accounting line for a customer."""

    class EntryType(models.TextChoices):
        DEBIT = "debit", _("Debit (udhaar / charge)")
        CREDIT = "credit", _("Credit (payment)")

    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="ledger_entries"
    )
    entry_type = models.CharField(max_length=10, choices=EntryType.choices)
    # Always stored positive; direction comes from entry_type.
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)

    description = models.CharField(max_length=255, blank=True)
    # Optional payment method label for CREDIT entries. The dynamic
    # PaymentMethod model arrives with the POS in Phase 4; kept as text here.
    method = models.CharField(max_length=40, blank=True)
    due_date = models.DateField(null=True, blank=True)
    # Loose link to a source document, e.g. "sale:42" (set by later phases).
    reference = models.CharField(max_length=60, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_ledger_entries",
    )

    class Meta:
        verbose_name_plural = "customer ledger entries"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["business", "customer", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.customer.name} {self.entry_type} {self.amount}"

    @property
    def debit_amount(self):
        return self.amount if self.entry_type == self.EntryType.DEBIT else None

    @property
    def credit_amount(self):
        return self.amount if self.entry_type == self.EntryType.CREDIT else None
