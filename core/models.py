"""
Shared model building blocks used across every Mera Hisaab app.

The central idea is tenant isolation: almost every business record must belong
to exactly one Business, and code should never be able to *accidentally* query
across tenants. ``TenantBaseModel`` + ``TenantManager`` make the correct thing
easy and the wrong thing explicit.
"""
from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    """Adds created/updated timestamps to any model."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantQuerySet(models.QuerySet):
    """QuerySet with an explicit, readable tenant filter."""

    def for_business(self, business):
        """Return only rows belonging to ``business``.

        ``business`` may be a Business instance or its id.
        """
        return self.filter(business=business)


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """Default manager for tenant-scoped models.

    Deliberately does NOT auto-filter by tenant globally: that pattern hides
    the tenant boundary and is easy to bypass. Instead, callers must be
    explicit with ``Model.objects.for_business(request.business)`` — the
    boundary is visible in every query.
    """


class TenantBaseModel(TimeStampedModel):
    """Abstract base for every model owned by a single Business.

    Subclasses automatically get:
      * a non-null ``business`` foreign key,
      * created/updated timestamps,
      * a tenant-aware manager exposing ``.for_business(...)``.
    """

    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        db_index=True,
    )

    objects = TenantManager()

    class Meta:
        abstract = True


class NumberSequence(models.Model):
    """Per-business, per-key, per-year monotonic counter for document numbers.

    Used to generate gap-safe, unique invoice/purchase numbers WITHOUT relying
    on ``count()`` (which is racy). The billing service locks the row with
    ``select_for_update`` before incrementing. See ``core.services.next_number``.
    """

    business = models.ForeignKey(
        "businesses.Business", on_delete=models.CASCADE, related_name="number_sequences"
    )
    key = models.CharField(max_length=20)  # e.g. "sale", "purchase"
    year = models.PositiveIntegerField()
    last_value = models.PositiveIntegerField(default=0)

    objects = TenantManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["business", "key", "year"], name="unique_sequence_per_scope"
            )
        ]

    def __str__(self):
        return f"{self.business_id}:{self.key}:{self.year}={self.last_value}"


class SoftDeleteModel(models.Model):
    """Catalog-style models use ``is_active`` instead of hard deletes."""

    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        abstract = True

    def deactivate(self, *, save=True):
        self.is_active = False
        if save:
            self.save(update_fields=["is_active", "updated_at"])
