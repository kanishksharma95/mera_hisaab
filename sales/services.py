"""
Billing service — the single, authoritative way to create a sale.

Guarantees (all inside one ``transaction.atomic`` block):
  * every monetary value is computed on the backend (client numbers are never
    trusted);
  * a unique per-business invoice number is generated race-safely;
  * stock is decremented through the EXISTING inventory service (so a
    StockMovement/InventoryTransaction is always logged);
  * any unpaid balance is posted to the EXISTING customer ledger as udhaar;
  * cash-like payments are recorded as Payment rows.

If anything fails, the whole sale rolls back — no orphan stock or ledger rows.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.services import next_number
from customers.services import record_charge
from inventory.models import InventoryTransaction
from inventory.services import record_transaction
from payments.models import Payment, PaymentMethod
from products.models import Product

from .models import Sale, SaleItem

TWOPLACES = Decimal("0.01")


def _money(value):
    return Decimal(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _compute_line(*, unit_price, quantity, discount, tax_percent, price_includes_tax):
    """Return (net, tax, line_total) for one item, all 2-dp Decimals."""
    unit_price = Decimal(unit_price)
    quantity = Decimal(quantity)
    discount = Decimal(discount or 0)
    rate = Decimal(tax_percent or 0)

    gross_before_discount = unit_price * quantity
    if price_includes_tax and rate > 0:
        # unit_price already includes tax; split it out.
        taxable_gross = gross_before_discount - discount
        net = taxable_gross / (Decimal("1") + rate / Decimal("100"))
        tax = taxable_gross - net
        line_total = taxable_gross
    else:
        net = gross_before_discount - discount
        tax = net * rate / Decimal("100")
        line_total = net + tax
    return _money(net), _money(tax), _money(line_total)


@transaction.atomic
def create_sale(*, business, user, items, customer=None, order_discount=0,
                payments=None, notes=""):
    """Create a sale and everything that hangs off it, atomically.

    ``items``:    list of {"product": Product|id, "quantity", "unit_price"?,
                  "discount"?}
    ``payments``: list of {"method": PaymentMethod|id, "amount"} — cash-like
                  amounts actually received. Any shortfall becomes udhaar.
    """
    if not items:
        raise ValidationError("Add at least one product to the sale.")

    price_includes_tax = business.prices_include_tax
    order_discount = _money(order_discount or 0)

    # --- Resolve + validate items (tenant-scoped) ---
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

        unit_price = Decimal(row.get("unit_price", product.selling_price))
        if unit_price < 0:
            raise ValidationError("Price cannot be negative.")
        discount = Decimal(row.get("discount", 0) or 0)
        if discount < 0:
            raise ValidationError(f"Discount for {product.name} cannot be negative.")
        if discount > unit_price * quantity:
            raise ValidationError(
                f"Discount for {product.name} cannot exceed the line amount."
            )

        net, tax, line_total = _compute_line(
            unit_price=unit_price, quantity=quantity, discount=discount,
            tax_percent=product.tax_percent, price_includes_tax=price_includes_tax,
        )
        resolved.append({
            "product": product, "quantity": quantity, "unit_price": _money(unit_price),
            "cost_price": _money(product.purchase_price), "discount": _money(discount),
            "tax_percent": product.tax_percent, "tax": tax, "net": net,
            "line_total": line_total,
        })

    subtotal = _money(sum(r["net"] for r in resolved))
    tax_total = _money(sum(r["tax"] for r in resolved))
    line_discounts = _money(sum(r["discount"] for r in resolved))
    gross = _money(subtotal + tax_total)

    if order_discount < 0 or order_discount > gross:
        raise ValidationError("Invalid order discount.")
    total = _money(gross - order_discount)
    discount_total = _money(line_discounts + order_discount)

    # --- Payments received (cash-like) ---
    received = Decimal("0.00")
    payment_rows = []
    for p in (payments or []):
        method = p["method"]
        if not isinstance(method, PaymentMethod):
            method = PaymentMethod.objects.for_business(business).filter(pk=method).first()
        if method is None or method.business_id != business.id:
            raise ValidationError("Invalid payment method.")
        amount = _money(p["amount"])
        if amount <= 0:
            continue
        if method.is_credit:
            # Credit is not money received; it becomes udhaar below.
            continue
        received += amount
        payment_rows.append((method, amount))

    # Cap recorded paid amount at the total (physical change is not tracked).
    paid_amount = min(received, total)
    due_amount = _money(total - paid_amount)

    if due_amount > 0 and customer is None:
        raise ValidationError("Select a customer to record the balance as udhaar.")

    if customer is not None and customer.business_id != business.id:
        raise ValidationError("Invalid customer for this shop.")

    if due_amount > 0:
        status = Sale.PaymentStatus.UNPAID if paid_amount == 0 else Sale.PaymentStatus.PARTIAL
    else:
        status = Sale.PaymentStatus.PAID

    # --- Persist ---
    year = timezone.now().year
    invoice_number, seq = next_number(
        business=business, key="sale", year=year, prefix=business.invoice_prefix or "MH"
    )

    sale = Sale.objects.create(
        business=business, invoice_number=invoice_number, invoice_seq=seq,
        customer=customer, subtotal=subtotal, discount_total=discount_total,
        order_discount=order_discount, tax_total=tax_total, total=total,
        paid_amount=paid_amount, due_amount=due_amount, payment_status=status,
        notes=notes, created_by=user,
    )

    for r in resolved:
        SaleItem.objects.create(
            business=business, sale=sale, product=r["product"],
            product_name=r["product"].name, quantity=r["quantity"],
            unit_price=r["unit_price"], cost_price=r["cost_price"],
            discount=r["discount"], tax_percent=r["tax_percent"],
            tax_amount=r["tax"], line_total=r["line_total"],
        )
        # Decrement stock via the existing inventory service (logs a movement).
        record_transaction(
            product=r["product"], kind=InventoryTransaction.Kind.SALE,
            quantity=-r["quantity"], reference=f"sale:{sale.id}",
            note=f"Sale {invoice_number}", user=user,
        )

    for method, amount in payment_rows:
        Payment.objects.create(
            business=business, direction=Payment.Direction.IN, method=method,
            amount=amount, sale=sale, customer=customer,
            reference=f"sale:{sale.id}", created_by=user,
        )

    if due_amount > 0:
        record_charge(
            customer=customer, amount=due_amount,
            description=f"Credit sale {invoice_number}",
            reference=f"sale:{sale.id}", user=user,
        )

    return sale
