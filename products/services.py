"""
Product catalog services.

Encapsulates all product and category creation, modification, and deactivation.
Never writes directly from external layers: always enforce tenant scoping,
validation, and soft-deletion.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from inventory.services import set_opening_stock
from .models import Product, ProductCategory


def create_category(*, business, name, description="", user=None):
    """Create a new product category for the given business."""
    name = (name or "").strip()
    if not name:
        raise ValidationError("Category name is required.")

    if ProductCategory.objects.for_business(business).filter(name__iexact=name).exists():
        raise ValidationError(f"Category '{name}' already exists.")

    return ProductCategory.objects.create(
        business=business,
        name=name,
        description=description or "",
    )


def rename_category(*, category, name, description=None, user=None):
    """Rename or update description of a category."""
    name = (name or "").strip()
    if not name:
        raise ValidationError("Category name cannot be empty.")

    conflict = (
        ProductCategory.objects.for_business(category.business)
        .filter(name__iexact=name)
        .exclude(pk=category.pk)
        .exists()
    )
    if conflict:
        raise ValidationError(f"Another category named '{name}' already exists.")

    category.name = name
    update_fields = ["name", "updated_at"]
    if description is not None:
        category.description = description
        update_fields.append("description")

    category.save(update_fields=update_fields)
    return category


def deactivate_category(*, category, user=None):
    """Soft-delete a product category."""
    category.deactivate()
    return category


@transaction.atomic
def create_product(
    *,
    business,
    name,
    sku="",
    barcode="",
    category=None,
    brand="",
    purchase_price=0,
    selling_price=0,
    tax_percent=0,
    unit="pcs",
    min_stock_level=0,
    opening_stock=0,
    user=None,
):
    """Create a new product and optionally record its opening stock transaction."""
    name = (name or "").strip()
    if not name:
        raise ValidationError("Product name is required.")

    sku = (sku or "").strip()
    barcode = (barcode or "").strip()

    if sku:
        if Product.objects.for_business(business).filter(sku=sku).exists():
            raise ValidationError(f"Product with SKU '{sku}' already exists.")

    if category is not None and category.business_id != business.id:
        raise ValidationError("Category does not belong to this business.")

    purchase_price = Decimal(str(purchase_price or 0))
    selling_price = Decimal(str(selling_price or 0))
    tax_percent = Decimal(str(tax_percent or 0))
    min_stock_level = Decimal(str(min_stock_level or 0))
    opening_stock = Decimal(str(opening_stock or 0))

    if purchase_price < 0 or selling_price < 0 or tax_percent < 0 or min_stock_level < 0:
        raise ValidationError("Prices, tax, and min stock cannot be negative.")

    product = Product.objects.create(
        business=business,
        name=name,
        sku=sku,
        barcode=barcode,
        category=category,
        brand=brand or "",
        purchase_price=purchase_price,
        selling_price=selling_price,
        tax_percent=tax_percent,
        unit=unit or "pcs",
        current_stock=Decimal("0.000"),
        min_stock_level=min_stock_level,
    )

    if opening_stock > 0:
        set_opening_stock(product=product, quantity=opening_stock, user=user)

    return product


def update_product(
    *,
    product,
    name=None,
    sku=None,
    barcode=None,
    category=None,
    brand=None,
    purchase_price=None,
    selling_price=None,
    tax_percent=None,
    unit=None,
    min_stock_level=None,
    user=None,
):
    """Update catalog fields of a product (current_stock is never updated directly)."""
    update_fields = ["updated_at"]

    if name is not None:
        name = name.strip()
        if not name:
            raise ValidationError("Product name cannot be empty.")
        product.name = name
        update_fields.append("name")

    if sku is not None:
        sku = sku.strip()
        if sku:
            conflict = (
                Product.objects.for_business(product.business)
                .filter(sku=sku)
                .exclude(pk=product.pk)
                .exists()
            )
            if conflict:
                raise ValidationError(f"Another product with SKU '{sku}' already exists.")
        product.sku = sku
        update_fields.append("sku")

    if barcode is not None:
        product.barcode = barcode.strip()
        update_fields.append("barcode")

    if category is not None:
        if category.business_id != product.business_id:
            raise ValidationError("Category does not belong to this business.")
        product.category = category
        update_fields.append("category")

    if brand is not None:
        product.brand = brand.strip()
        update_fields.append("brand")

    if purchase_price is not None:
        pp = Decimal(str(purchase_price))
        if pp < 0:
            raise ValidationError("Purchase price cannot be negative.")
        product.purchase_price = pp
        update_fields.append("purchase_price")

    if selling_price is not None:
        sp = Decimal(str(selling_price))
        if sp < 0:
            raise ValidationError("Selling price cannot be negative.")
        product.selling_price = sp
        update_fields.append("selling_price")

    if tax_percent is not None:
        tp = Decimal(str(tax_percent))
        if tp < 0:
            raise ValidationError("Tax percent cannot be negative.")
        product.tax_percent = tp
        update_fields.append("tax_percent")

    if unit is not None:
        unit = unit.strip()
        if not unit:
            raise ValidationError("Unit cannot be empty.")
        product.unit = unit
        update_fields.append("unit")

    if min_stock_level is not None:
        msl = Decimal(str(min_stock_level))
        if msl < 0:
            raise ValidationError("Min stock level cannot be negative.")
        product.min_stock_level = msl
        update_fields.append("min_stock_level")

    product.save(update_fields=update_fields)
    return product


def deactivate_product(*, product, user=None):
    """Soft-delete a product."""
    product.deactivate()
    return product

