"""
Business (tenant) models + the dynamic business-type/field system.

* ``BusinessType`` and ``BusinessTypeField`` are platform-global and managed by
  the Super Admin. They drive which extra product attributes a shop collects,
  WITHOUT any per-business-type Python code or templates.
* ``Business`` is the tenant. Every business-owned record links back to it.
* ``BusinessMembership`` links a User to a Business with a role, enabling one
  user to belong to several shops and controlling tenant access.
"""
from django.conf import settings
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from core.models import SoftDeleteModel, TenantManager, TimeStampedModel


class BusinessType(TimeStampedModel, SoftDeleteModel):
    """A category of business (Grocery, Garments, Mobile, ...).

    Stored in the DB and editable by the Super Admin — never hardcoded in
    business logic. Each type defines a set of dynamic product fields.
    """

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.CharField(max_length=255, blank=True)
    icon = models.CharField(
        max_length=50, blank=True, help_text=_("Optional emoji or icon name.")
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "name")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class BusinessTypeField(TimeStampedModel):
    """A dynamic product attribute definition for a business type.

    Example: for 'Mobile' -> {name: IMEI, type: text, required: True}. These
    appear automatically when adding products (wired in Phase 2).
    """

    class FieldType(models.TextChoices):
        TEXT = "text", _("Text")
        NUMBER = "number", _("Number")
        DATE = "date", _("Date")
        BOOLEAN = "boolean", _("Yes / No")
        SELECT = "select", _("Dropdown")

    business_type = models.ForeignKey(
        BusinessType, on_delete=models.CASCADE, related_name="fields"
    )
    name = models.CharField(max_length=100)
    field_type = models.CharField(
        max_length=20, choices=FieldType.choices, default=FieldType.TEXT
    )
    required = models.BooleanField(default=False)
    options = models.JSONField(
        blank=True,
        null=True,
        help_text=_("Choices for a dropdown field, as a JSON list of strings."),
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "name")
        constraints = [
            models.UniqueConstraint(
                fields=["business_type", "name"],
                name="unique_field_name_per_business_type",
            )
        ]

    def __str__(self):
        return f"{self.business_type.name} · {self.name}"


class Business(TimeStampedModel, SoftDeleteModel):
    """A tenant: one shop / small business."""

    class Currency(models.TextChoices):
        INR = "INR", _("Indian Rupee (₹)")
        USD = "USD", _("US Dollar ($)")

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True, blank=True)
    business_type = models.ForeignKey(
        BusinessType,
        on_delete=models.PROTECT,
        related_name="businesses",
        null=True,
        blank=True,
    )

    owner_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)

    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    pincode = models.CharField(max_length=12, blank=True)

    gst_number = models.CharField(_("GST number"), max_length=20, blank=True)
    logo = models.ImageField(upload_to="business_logos/", blank=True, null=True)

    currency = models.CharField(
        max_length=3, choices=Currency.choices, default=Currency.INR
    )
    # Default sales tax percentage applied to products unless overridden.
    default_tax_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )
    prices_include_tax = models.BooleanField(default=False)

    # Prefix for generated invoice numbers, e.g. "MH" -> MH-2026-000001.
    invoice_prefix = models.CharField(max_length=10, default="MH")

    class Meta:
        verbose_name_plural = "businesses"
        ordering = ("name",)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "business"
            slug = base
            i = 1
            while Business.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                i += 1
                slug = f"{base}-{i}"
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def currency_symbol(self):
        return {"INR": "₹", "USD": "$"}.get(self.currency, "")


class BusinessMembership(TimeStampedModel):
    """Links a user to a business with a role.

    Phase 1 uses a simple role string; Phase 8 upgrades this to a DB-backed
    Role/Permission model. Tenant access is decided entirely by the existence
    of an active membership — never by client-supplied ids.
    """

    class Role(models.TextChoices):
        OWNER = "owner", _("Owner")
        MANAGER = "manager", _("Manager")
        CASHIER = "cashier", _("Cashier")
        ACCOUNTANT = "accountant", _("Accountant")
        INVENTORY = "inventory", _("Inventory Manager")
        SALES = "sales", _("Sales Staff")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.OWNER)
    is_active = models.BooleanField(default=True)

    # BusinessMembership carries a `business` FK, so it exposes the same
    # tenant-scoping helper (`.for_business(...)`) used across the platform.
    objects = TenantManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "business"], name="unique_membership_per_user_business"
            )
        ]

    def __str__(self):
        return f"{self.user} @ {self.business} ({self.get_role_display()})"

    @property
    def is_owner(self):
        return self.role == self.Role.OWNER

    @property
    def is_manager(self):
        return self.role == self.Role.MANAGER

    @property
    def can_manage_team(self):
        return self.role in (self.Role.OWNER, self.Role.MANAGER)

    @property
    def can_manage_settings(self):
        return self.role == self.Role.OWNER

    @property
    def can_view_reports(self):
        return self.role in (self.Role.OWNER, self.Role.MANAGER, self.Role.ACCOUNTANT)

    @property
    def can_manage_expenses(self):
        return self.role in (self.Role.OWNER, self.Role.MANAGER, self.Role.ACCOUNTANT)

    @property
    def can_manage_inventory(self):
        return self.role in (self.Role.OWNER, self.Role.MANAGER, self.Role.INVENTORY, self.Role.ACCOUNTANT)

    @property
    def can_access_pos(self):
        return self.role in (self.Role.OWNER, self.Role.MANAGER, self.Role.CASHIER, self.Role.SALES)

    @property
    def can_manage_customers(self):
        return self.role in (self.Role.OWNER, self.Role.MANAGER, self.Role.CASHIER, self.Role.SALES, self.Role.ACCOUNTANT)

    @property
    def can_manage_suppliers(self):
        return self.role in (self.Role.OWNER, self.Role.MANAGER, self.Role.INVENTORY, self.Role.ACCOUNTANT)

