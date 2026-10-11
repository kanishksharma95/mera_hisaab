"""
Payments: a dynamic, per-business list of payment methods and the payment
records that reference them.

Payment methods are NOT hardcoded in business logic — each business gets an
editable set (seeded lazily with sensible defaults). ``Payment`` is shared:
sales record money coming IN; purchases (Phase 5) will record money going OUT.
"""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import SoftDeleteModel, TenantBaseModel, TimeStampedModel

# Default methods seeded for a new business. Seed data, not business logic —
# the shopkeeper can add/rename/deactivate these from settings later.
DEFAULT_PAYMENT_METHODS = [
    ("Cash", "cash", True),
    ("UPI", "upi", True),
    ("Card", "card", True),
    ("Bank Transfer", "bank", True),
    ("Credit / Udhaar", "credit", False),
    ("Other", "other", True),
]


class PaymentMethod(TenantBaseModel, SoftDeleteModel):
    """A payment method available to one business (dynamic, editable)."""

    name = models.CharField(max_length=50)
    # Stable machine code; "credit" is treated specially (routes to udhaar).
    code = models.CharField(max_length=20)
    # Whether receiving via this method adds to the cash/bank drawer (Credit
    # does not — it becomes a receivable instead).
    is_cash_like = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "name")
        constraints = [
            models.UniqueConstraint(
                fields=["business", "code"], name="unique_payment_code_per_business"
            )
        ]

    def __str__(self):
        return self.name

    @property
    def is_credit(self):
        return self.code == "credit"


class Payment(TenantBaseModel):
    """A money movement recorded against a sale (and later, a purchase)."""

    class Direction(models.TextChoices):
        IN = "in", _("Received")
        OUT = "out", _("Paid out")

    direction = models.CharField(
        max_length=3, choices=Direction.choices, default=Direction.IN
    )
    method = models.ForeignKey(
        PaymentMethod, on_delete=models.PROTECT, related_name="payments"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    # Optional links to source documents (kept nullable + generic so the model
    # is reused across modules without tight coupling).
    sale = models.ForeignKey(
        "sales.Sale", on_delete=models.CASCADE, null=True, blank=True,
        related_name="payments",
    )
    purchase = models.ForeignKey(
        "purchases.Purchase", on_delete=models.CASCADE, null=True, blank=True,
        related_name="payments",
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="payments",
    )
    supplier = models.ForeignKey(
        "suppliers.Supplier", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="payments",
    )
    reference = models.CharField(max_length=60, blank=True)
    note = models.CharField(max_length=255, blank=True)

    # Gateway (Razorpay) traceability. Blank for cash/manual payments. The
    # payment id is what makes a gateway payment idempotent across retries and
    # the webhook-vs-callback race.
    razorpay_order_id = models.CharField(max_length=40, blank=True)
    razorpay_payment_id = models.CharField(max_length=40, blank=True, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="payments_recorded",
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["business", "-created_at"])]
        constraints = [
            # A given Razorpay payment can be recorded at most once per business.
            models.UniqueConstraint(
                fields=["business", "razorpay_payment_id"],
                condition=~models.Q(razorpay_payment_id=""),
                name="unique_razorpay_payment_per_business",
            )
        ]

    def __str__(self):
        return f"{self.get_direction_display()} {self.amount} ({self.method})"


# SaaS plan catalog. Kept in code (not the DB) because plans are a product
# decision, not per-tenant data. ``amount`` is in rupees; ``interval`` matches
# Razorpay's period vocabulary. The matching Razorpay Plan is created on demand.
SAAS_PLANS = {
    "basic_monthly": {"name": "Basic (Monthly)", "amount": 199, "period": "monthly", "interval": 1},
    "pro_monthly": {"name": "Pro (Monthly)", "amount": 499, "period": "monthly", "interval": 1},
    "pro_yearly": {"name": "Pro (Yearly)", "amount": 4999, "period": "yearly", "interval": 1},
}


class BusinessSubscription(TimeStampedModel):
    """One business's SaaS subscription to Mera Hisaab, backed by Razorpay.

    A business has at most one subscription record; its ``status`` mirrors the
    Razorpay subscription lifecycle, driven by webhooks (source of truth).
    """

    class Status(models.TextChoices):
        CREATED = "created", _("Created")
        AUTHENTICATED = "authenticated", _("Authenticated")
        ACTIVE = "active", _("Active")
        PENDING = "pending", _("Pending")
        HALTED = "halted", _("Halted")
        CANCELLED = "cancelled", _("Cancelled")
        COMPLETED = "completed", _("Completed")

    business = models.OneToOneField(
        "businesses.Business", on_delete=models.CASCADE, related_name="subscription"
    )
    plan_code = models.CharField(max_length=40)
    razorpay_plan_id = models.CharField(max_length=40, blank=True)
    razorpay_subscription_id = models.CharField(max_length=40, blank=True, db_index=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.CREATED
    )
    current_period_end = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="subscriptions_created",
    )

    def __str__(self):
        return f"{self.business} · {self.plan_code} ({self.get_status_display()})"

    @property
    def is_active(self):
        return self.status in (self.Status.ACTIVE, self.Status.AUTHENTICATED)

    @property
    def plan(self):
        return SAAS_PLANS.get(self.plan_code, {})
