"""
Expenses: a dynamic, per-business list of expense categories and the expense
records booked against them.

Categories are NOT hardcoded in business logic — each business gets an editable
set (seeded lazily with sensible defaults), exactly like payment methods. Every
expense also records a money-OUT ``Payment`` so the cashbook stays complete.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import SoftDeleteModel, TenantBaseModel

# Seeded for a new business; fully editable by the shopkeeper afterwards.
DEFAULT_EXPENSE_CATEGORIES = [
    "Rent",
    "Electricity",
    "Salaries",
    "Transport",
    "Packaging",
    "Tea & Snacks",
    "Repairs & Maintenance",
    "Miscellaneous",
]


class ExpenseCategory(TenantBaseModel, SoftDeleteModel):
    """An expense category available to one business (dynamic, editable)."""

    name = models.CharField(max_length=60)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "name")
        verbose_name_plural = "expense categories"
        constraints = [
            models.UniqueConstraint(
                fields=["business", "name"],
                name="unique_expense_category_per_business",
            )
        ]

    def __str__(self):
        return self.name


class Expense(TenantBaseModel):
    """A single expense booked by the business."""

    category = models.ForeignKey(
        ExpenseCategory, on_delete=models.PROTECT, related_name="expenses"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    # How it was paid — reuses the shared payment methods.
    method = models.ForeignKey(
        "payments.PaymentMethod", on_delete=models.PROTECT,
        related_name="expenses", null=True, blank=True,
    )
    spent_on = models.DateField(default=timezone.localdate)
    note = models.CharField(max_length=255, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="expenses_recorded",
    )

    class Meta:
        ordering = ("-spent_on", "-created_at")
        indexes = [models.Index(fields=["business", "-spent_on"])]

    def __str__(self):
        return f"{self.category} · {self.amount}"
