"""
Product catalog: categories, products, and dynamic per-business-type attributes.

Stock quantities use Decimal (decimal_places=3) so shops selling by weight/volume
(kg, litre) work as well as unit-based shops. Money uses Decimal(…, 2).
Current stock is maintained here but every change is logged as an
``inventory.InventoryTransaction`` (see the inventory app's services).
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import SoftDeleteModel, TenantBaseModel, TimeStampedModel


class ProductCategory(TenantBaseModel, SoftDeleteModel):
    """A business-specific product category (Rice, Shirts, …)."""

    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name_plural = "product categories"
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=["business", "name"], name="unique_category_name_per_business"
            )
        ]

    def __str__(self):
        return self.name


class Product(TenantBaseModel, SoftDeleteModel):
    """A sellable product/item belonging to one business."""

    name = models.CharField(max_length=200, db_index=True)
    sku = models.CharField(_("SKU"), max_length=60, blank=True)
    barcode = models.CharField(max_length=60, blank=True)
    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    brand = models.CharField(max_length=100, blank=True)

    purchase_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    unit = models.CharField(max_length=20, default="pcs")

    # Quantities support fractional units (e.g. 1.5 kg).
    current_stock = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    min_stock_level = models.DecimalField(max_digits=12, decimal_places=3, default=0)

    image = models.ImageField(upload_to="product_images/", blank=True, null=True)

    class Meta:
        ordering = ("name",)
        indexes = [
            models.Index(fields=["business", "name"]),
            models.Index(fields=["business", "sku"]),
            models.Index(fields=["business", "barcode"]),
        ]
        constraints = [
            # SKU is unique per business when provided (blank SKUs are allowed).
            models.UniqueConstraint(
                fields=["business", "sku"],
                condition=~models.Q(sku=""),
                name="unique_sku_per_business",
            )
        ]

    def __str__(self):
        return self.name

    @property
    def is_low_stock(self):
        return self.current_stock <= self.min_stock_level

    @property
    def profit_per_unit(self):
        return self.selling_price - self.purchase_price

    @property
    def stock_value(self):
        """Stock valued at purchase price (used in inventory reports later)."""
        return (self.current_stock * self.purchase_price).quantize(Decimal("0.01"))


class ProductAttributeValue(TimeStampedModel):
    """Value of a dynamic BusinessTypeField for a specific product.

    This is what makes products polymorphic without per-type tables: a Mobile
    shop stores IMEI/Model here, a Garments shop stores Size/Color, etc. The
    field definitions come from ``businesses.BusinessTypeField`` (Phase 1).
    """

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="attributes"
    )
    field = models.ForeignKey(
        "businesses.BusinessTypeField",
        on_delete=models.CASCADE,
        related_name="values",
    )
    value = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product", "field"], name="unique_attribute_per_product"
            )
        ]

    def __str__(self):
        return f"{self.product.name} · {self.field.name}: {self.value}"
