"""
Purchase service — the single authoritative way to record a purchase (stock-in).

Same discipline as the billing service: all money computed on the backend,
one atomic transaction, and it REUSES the inventory + supplier-ledger +
payment building blocks rather than duplicating them.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.services import next_number
from inventory.models import InventoryTransaction
from inventory.services import record_transaction
from payments.models import Payment, PaymentMethod
from products.models import Product
from suppliers.services import record_bill, record_payment as supplier_payment

from .models import Purchase, PurchaseItem

TWOPLACES = Decimal("0.01")


def _money(value):
    return Decimal(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


@transaction.atomic
def create_purchase(*, business, user, items, supplier=None, order_discount=0,
                    payments=None, supplier_invoice="", notes="",
                    update_cost=True):
    """Record a purchase, increase stock, and update the supplier ledger.

    ``items``: [{"product": Product|id, "quantity", "unit_cost", "discount"?,
                 "tax_percent"?}]
    ``payments``: [{"method": PaymentMethod|id, "amount"}] paid to the supplier now.
    """
    if not items:
        raise ValidationError("Add at least one product to the purchase.")

    if supplier is not None and supplier.business_id != business.id:
        raise ValidationError("Invalid supplier for this shop.")

    resolved = []
    for row in items:
        product = row["product"]
        if not isinstance(product, Product):
            product = Product.objects.for_business(business).filter(pk=product).first()
        elif product.business_id != business.id:
            product = None
        if product is None:
            raise ValidationError("One or more products are invalid for this shop.")

        quantity = Decimal(row["quantity"])
        if quantity <= 0:
            raise ValidationError(f"Quantity for {product.name} must be positive.")
        unit_cost = Decimal(row.get("unit_cost", product.purchase_price))
        if unit_cost < 0:
            raise ValidationError("Cost cannot be negative.")
        discount = Decimal(row.get("discount", 0) or 0)
        if discount < 0:
            raise ValidationError(f"Discount for {product.name} cannot be negative.")
        if discount > unit_cost * quantity:
            raise ValidationError(
                f"Discount for {product.name} cannot exceed the line amount."
            )
        rate = Decimal(row.get("tax_percent", product.tax_percent) or 0)
        if rate < 0 or rate > 100:
            raise ValidationError("Tax % must be between 0 and 100.")

        net = unit_cost * quantity - discount
        tax = net * rate / Decimal("100")
        line_total = net + tax
        resolved.append({
            "product": product, "quantity": quantity, "unit_cost": _money(unit_cost),
            "discount": _money(discount), "tax_percent": rate, "tax": _money(tax),
            "net": _money(net), "line_total": _money(line_total),
        })

    subtotal = _money(sum(r["net"] for r in resolved))
    tax_total = _money(sum(r["tax"] for r in resolved))
    line_discounts = _money(sum(r["discount"] for r in resolved))
    gross = _money(subtotal + tax_total)

    order_discount = _money(order_discount or 0)
    if order_discount < 0 or order_discount > gross:
        raise ValidationError("Invalid order discount.")
    total = _money(gross - order_discount)
    discount_total = _money(line_discounts + order_discount)

    # Payments made to the supplier now (cash-like only; credit => payable).
    paid = Decimal("0.00")
    payment_rows = []
    for p in (payments or []):
        method = p["method"]
        if not isinstance(method, PaymentMethod):
            method = PaymentMethod.objects.for_business(business).filter(pk=method).first()
        if method is None or method.business_id != business.id:
            raise ValidationError("Invalid payment method.")
        amount = _money(p["amount"])
        if amount <= 0 or method.is_credit:
            continue
        paid += amount
        payment_rows.append((method, amount))

    paid_amount = min(paid, total)
    due_amount = _money(total - paid_amount)

    if due_amount > 0 and supplier is None:
        raise ValidationError("Select a supplier to record the balance as payable.")

    if due_amount > 0:
        status = Purchase.PaymentStatus.UNPAID if paid_amount == 0 else Purchase.PaymentStatus.PARTIAL
    else:
        status = Purchase.PaymentStatus.PAID

    year = timezone.now().year
    number, seq = next_number(business=business, key="purchase", year=year, prefix="PUR")

    purchase = Purchase.objects.create(
        business=business, number=number, number_seq=seq, supplier=supplier,
        supplier_invoice=supplier_invoice, subtotal=subtotal,
        discount_total=discount_total, order_discount=order_discount,
        tax_total=tax_total, total=total, paid_amount=paid_amount,
        due_amount=due_amount, payment_status=status, notes=notes, created_by=user,
    )

    for r in resolved:
        product = r["product"]
        PurchaseItem.objects.create(
            business=business, purchase=purchase, product=product,
            product_name=product.name, quantity=r["quantity"],
            unit_cost=r["unit_cost"], discount=r["discount"],
            tax_percent=r["tax_percent"], tax_amount=r["tax"], line_total=r["line_total"],
        )
        # Increase stock through the existing inventory service.
        record_transaction(
            product=product, kind=InventoryTransaction.Kind.PURCHASE,
            quantity=r["quantity"], reference=f"purchase:{purchase.id}",
            note=f"Purchase {number}", user=user,
        )
        # Keep the product's cost current for accurate future COGS.
        if update_cost and product.purchase_price != r["unit_cost"]:
            product.purchase_price = r["unit_cost"]
            product.save(update_fields=["purchase_price", "updated_at"])

    # Supplier ledger: full bill increases payable, then payments reduce it.
    if supplier is not None:
        record_bill(
            supplier=supplier, amount=total, description=f"Purchase {number}",
            reference=f"purchase:{purchase.id}", user=user,
        )

    for method, amount in payment_rows:
        Payment.objects.create(
            business=business, direction=Payment.Direction.OUT, method=method,
            amount=amount, purchase=purchase, supplier=supplier,
            reference=f"purchase:{purchase.id}", created_by=user,
        )
        if supplier is not None:
            supplier_payment(
                supplier=supplier, amount=amount, method=method.name,
                description=f"Payment for {number}",
                reference=f"purchase:{purchase.id}", user=user,
            )

    return purchase
