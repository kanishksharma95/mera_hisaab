"""
Write operations for Mera Hisaab ADK Agent.

STRICT DISCIPLINE:
1. Agent NEVER writes to the DB directly (no .save(), .create(), .update(), .delete(), raw SQL).
2. ALL writes strictly route through the respective Django app services (services.py).
3. All operations are tenant-scoped and pass actor user to the service.
"""
from decimal import Decimal
from typing import Any, Dict, List, Optional
from django.db.models import Q

from .context import get_actor, get_business, require_permission
from .django_setup import init_django


def record_sale(
    *,
    items: List[Dict[str, Any]],
    customer_id_or_name: Optional[str] = None,
    cash_amount: float = 0.0,
    upi_amount: float = 0.0,
    order_discount: float = 0.0,
    notes: str = "",
) -> Dict[str, Any]:
    """Create a sale atomically through sales.services.create_sale.
    
    `items` format: [{"product_id_or_name": "...", "quantity": 2, "unit_price": 50.0}]
    """
    require_permission("can_access_pos")
    business = get_business()
    actor = get_actor()
    init_django()

    from customers.models import Customer
    from payments.models import PaymentMethod
    from products.models import Product
    from sales.services import create_sale

    # 1. Resolve Customer if provided
    customer = None
    if customer_id_or_name:
        cid = str(customer_id_or_name).strip()
        qs = Customer.objects.for_business(business).filter(is_active=True)
        if cid.isdigit():
            customer = qs.filter(pk=int(cid)).first()
        if not customer:
            customer = qs.filter(Q(name__iexact=cid) | Q(phone__iexact=cid)).first()
        if not customer:
            customer = qs.filter(name__icontains=cid).first()
        if not customer:
            raise ValueError(f"Customer '{customer_id_or_name}' not found for this shop.")

    # 2. Resolve items
    service_items = []
    for item in items:
        p_ref = str(item.get("product_id_or_name") or item.get("product") or "").strip()
        p_qs = Product.objects.for_business(business).filter(is_active=True)
        product = None
        if p_ref.isdigit():
            product = p_qs.filter(pk=int(p_ref)).first()
        if not product:
            product = p_qs.filter(Q(name__iexact=p_ref) | Q(sku__iexact=p_ref) | Q(barcode__iexact=p_ref)).first()
        if not product:
            product = p_qs.filter(name__icontains=p_ref).first()
        if not product:
            raise ValueError(f"Product '{p_ref}' not found in active inventory.")

        qty = Decimal(str(item.get("quantity", 1)))
        price = item.get("unit_price")
        unit_price = Decimal(str(price)) if price is not None else product.selling_price
        discount = Decimal(str(item.get("discount", 0) or 0))

        service_items.append({
            "product": product,
            "quantity": qty,
            "unit_price": unit_price,
            "discount": discount,
        })

    # 3. Resolve payments
    payments = []
    if cash_amount and Decimal(str(cash_amount)) > 0:
        cash_method = PaymentMethod.objects.for_business(business).filter(code="cash").first()
        if not cash_method:
            cash_method = PaymentMethod.objects.for_business(business).filter(name__icontains="cash").first()
        if cash_method:
            payments.append({"method": cash_method, "amount": Decimal(str(cash_amount))})

    if upi_amount and Decimal(str(upi_amount)) > 0:
        upi_method = PaymentMethod.objects.for_business(business).filter(code="upi").first()
        if not upi_method:
            upi_method = PaymentMethod.objects.for_business(business).filter(name__icontains="upi").first()
        if upi_method:
            payments.append({"method": upi_method, "amount": Decimal(str(upi_amount))})

    # 4. Invoke service
    sale = create_sale(
        business=business,
        user=actor,
        items=service_items,
        customer=customer,
        order_discount=Decimal(str(order_discount or 0)),
        payments=payments,
        notes=notes or "Created via ADK Agent",
    )

    return {
        "id": sale.id,
        "invoice_number": sale.invoice_number,
        "total": str(sale.total),
        "paid_amount": str(sale.paid_amount),
        "due_amount": str(sale.due_amount),
        "payment_status": sale.payment_status,
        "customer": sale.customer.name if sale.customer else "Walk-in",
    }


def record_customer_payment(
    *,
    customer_id_or_name: str,
    amount: float,
    method: str = "Cash",
    description: str = "",
) -> Dict[str, Any]:
    """Record payment received from a customer to reduce their pending udhaar."""
    require_permission("can_manage_customers")
    business = get_business()
    actor = get_actor()
    init_django()

    from customers.models import Customer
    from customers.services import record_payment

    cid = str(customer_id_or_name).strip()
    qs = Customer.objects.for_business(business).filter(is_active=True)
    customer = None
    if cid.isdigit():
        customer = qs.filter(pk=int(cid)).first()
    if not customer:
        customer = qs.filter(Q(name__iexact=cid) | Q(phone__iexact=cid)).first()
    if not customer:
        customer = qs.filter(name__icontains=cid).first()
    if not customer:
        raise ValueError(f"Customer '{customer_id_or_name}' not found.")

    dec_amount = Decimal(str(amount))
    if dec_amount <= 0:
        raise ValueError("Payment amount must be positive.")

    entry = record_payment(
        customer=customer,
        amount=dec_amount,
        method=method or "Cash",
        description=description or "Payment received via ADK Agent",
        user=actor,
    )
    customer.refresh_from_db()

    return {
        "customer_id": customer.id,
        "customer_name": customer.name,
        "amount_paid": str(dec_amount),
        "new_balance": str(customer.current_balance),
        "reference": entry.reference or f"payment:{entry.id}",
    }


def record_customer_charge(
    *,
    customer_id_or_name: str,
    amount: float,
    description: str = "",
) -> Dict[str, Any]:
    """Record manual udhaar / debit charge against a customer."""
    require_permission("can_manage_customers")
    business = get_business()
    actor = get_actor()
    init_django()

    from customers.models import Customer
    from customers.services import record_charge

    cid = str(customer_id_or_name).strip()
    qs = Customer.objects.for_business(business).filter(is_active=True)
    customer = None
    if cid.isdigit():
        customer = qs.filter(pk=int(cid)).first()
    if not customer:
        customer = qs.filter(Q(name__iexact=cid) | Q(phone__iexact=cid)).first()
    if not customer:
        customer = qs.filter(name__icontains=cid).first()
    if not customer:
        raise ValueError(f"Customer '{customer_id_or_name}' not found.")

    dec_amount = Decimal(str(amount))
    if dec_amount <= 0:
        raise ValueError("Charge amount must be positive.")

    entry = record_charge(
        customer=customer,
        amount=dec_amount,
        description=description or "Manual udhaar added via ADK Agent",
        user=actor,
    )
    customer.refresh_from_db()

    return {
        "customer_id": customer.id,
        "customer_name": customer.name,
        "charge_amount": str(dec_amount),
        "new_balance": str(customer.current_balance),
        "reference": entry.reference or f"charge:{entry.id}",
    }


def create_new_customer(
    *,
    name: str,
    phone: str = "",
    email: str = "",
    address: str = "",
    credit_limit: float = 0.0,
    notes: str = "",
) -> Dict[str, Any]:
    """Create a new customer profile via customers.services.create_customer."""
    require_permission("can_manage_customers")
    business = get_business()
    actor = get_actor()
    init_django()

    from customers.services import create_customer

    customer = create_customer(
        business=business,
        name=name,
        phone=phone,
        email=email,
        address=address,
        credit_limit=Decimal(str(credit_limit or 0)),
        notes=notes,
        user=actor,
    )

    return {
        "id": customer.id,
        "name": customer.name,
        "phone": customer.phone,
        "current_balance": str(customer.current_balance),
        "credit_limit": str(customer.credit_limit),
    }


def update_existing_customer(
    *,
    customer_id_or_name: str,
    name: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    address: Optional[str] = None,
    credit_limit: Optional[float] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Update profile details of an existing customer via customers.services.update_customer."""
    require_permission("can_manage_customers")
    business = get_business()
    actor = get_actor()
    init_django()

    from customers.models import Customer
    from customers.services import update_customer

    cid = str(customer_id_or_name).strip()
    qs = Customer.objects.for_business(business).filter(is_active=True)
    customer = None
    if cid.isdigit():
        customer = qs.filter(pk=int(cid)).first()
    if not customer:
        customer = qs.filter(Q(name__iexact=cid) | Q(phone__iexact=cid)).first()
    if not customer:
        customer = qs.filter(name__icontains=cid).first()
    if not customer:
        raise ValueError(f"Customer '{customer_id_or_name}' not found.")

    dec_limit = Decimal(str(credit_limit)) if credit_limit is not None else None
    updated = update_customer(
        customer=customer,
        name=name,
        phone=phone,
        email=email,
        address=address,
        credit_limit=dec_limit,
        notes=notes,
        user=actor,
    )

    return {
        "id": updated.id,
        "name": updated.name,
        "phone": updated.phone,
        "credit_limit": str(updated.credit_limit),
        "current_balance": str(updated.current_balance),
    }


def deactivate_existing_customer(*, customer_id_or_name: str) -> Dict[str, Any]:
    """Soft-delete an active customer via customers.services.deactivate_customer."""
    require_permission("can_manage_customers")
    business = get_business()
    actor = get_actor()
    init_django()

    from customers.models import Customer
    from customers.services import deactivate_customer

    cid = str(customer_id_or_name).strip()
    qs = Customer.objects.for_business(business).filter(is_active=True)
    customer = None
    if cid.isdigit():
        customer = qs.filter(pk=int(cid)).first()
    if not customer:
        customer = qs.filter(Q(name__iexact=cid) | Q(phone__iexact=cid)).first()
    if not customer:
        customer = qs.filter(name__icontains=cid).first()
    if not customer:
        raise ValueError(f"Customer '{customer_id_or_name}' not found.")

    deactivate_customer(customer=customer, user=actor)
    return {"id": customer.id, "name": customer.name, "is_active": False}


def create_new_product(
    *,
    name: str,
    selling_price: float,
    purchase_price: float = 0.0,
    sku: str = "",
    barcode: str = "",
    category_name: Optional[str] = None,
    brand: str = "",
    unit: str = "pcs",
    opening_stock: float = 0.0,
    min_stock_level: float = 0.0,
    tax_percent: float = 0.0,
) -> Dict[str, Any]:
    """Create a new product via products.services.create_product."""
    require_permission("can_manage_inventory")
    business = get_business()
    actor = get_actor()
    init_django()

    from products.models import ProductCategory
    from products.services import create_category, create_product

    category = None
    if category_name:
        cname = category_name.strip()
        cat = ProductCategory.objects.for_business(business).filter(name__iexact=cname).first()
        if not cat:
            cat = create_category(business=business, name=cname, user=actor)
        category = cat

    prod = create_product(
        business=business,
        name=name,
        sku=sku or "",
        barcode=barcode or "",
        category=category,
        brand=brand or "",
        purchase_price=Decimal(str(purchase_price or 0)),
        selling_price=Decimal(str(selling_price or 0)),
        tax_percent=Decimal(str(tax_percent or 0)),
        unit=unit or "pcs",
        min_stock_level=Decimal(str(min_stock_level or 0)),
        opening_stock=Decimal(str(opening_stock or 0)),
        user=actor,
    )

    return {
        "id": prod.id,
        "name": prod.name,
        "sku": prod.sku,
        "selling_price": str(prod.selling_price),
        "current_stock": str(prod.current_stock),
        "unit": prod.unit,
        "category": prod.category.name if prod.category else None,
    }


def update_existing_product(
    *,
    product_id_or_sku: str,
    name: Optional[str] = None,
    selling_price: Optional[float] = None,
    purchase_price: Optional[float] = None,
    sku: Optional[str] = None,
    min_stock_level: Optional[float] = None,
    unit: Optional[str] = None,
) -> Dict[str, Any]:
    """Update catalog attributes of an existing product via products.services.update_product."""
    require_permission("can_manage_inventory")
    business = get_business()
    actor = get_actor()
    init_django()

    from products.models import Product
    from products.services import update_product

    pid = str(product_id_or_sku).strip()
    qs = Product.objects.for_business(business).filter(is_active=True)
    product = None
    if pid.isdigit():
        product = qs.filter(pk=int(pid)).first()
    if not product:
        product = qs.filter(Q(sku__iexact=pid) | Q(name__iexact=pid)).first()
    if not product:
        product = qs.filter(name__icontains=pid).first()
    if not product:
        raise ValueError(f"Product '{product_id_or_sku}' not found.")

    dec_sp = Decimal(str(selling_price)) if selling_price is not None else None
    dec_pp = Decimal(str(purchase_price)) if purchase_price is not None else None
    dec_msl = Decimal(str(min_stock_level)) if min_stock_level is not None else None

    updated = update_product(
        product=product,
        name=name,
        sku=sku,
        purchase_price=dec_pp,
        selling_price=dec_sp,
        min_stock_level=dec_msl,
        unit=unit,
        user=actor,
    )

    return {
        "id": updated.id,
        "name": updated.name,
        "sku": updated.sku,
        "selling_price": str(updated.selling_price),
        "purchase_price": str(updated.purchase_price),
        "current_stock": str(updated.current_stock),
    }


def deactivate_existing_product(*, product_id_or_sku: str) -> Dict[str, Any]:
    """Soft-delete an active product via products.services.deactivate_product."""
    require_permission("can_manage_inventory")
    business = get_business()
    actor = get_actor()
    init_django()

    from products.models import Product
    from products.services import deactivate_product

    pid = str(product_id_or_sku).strip()
    qs = Product.objects.for_business(business).filter(is_active=True)
    product = None
    if pid.isdigit():
        product = qs.filter(pk=int(pid)).first()
    if not product:
        product = qs.filter(Q(sku__iexact=pid) | Q(name__iexact=pid)).first()
    if not product:
        product = qs.filter(name__icontains=pid).first()
    if not product:
        raise ValueError(f"Product '{product_id_or_sku}' not found.")

    deactivate_product(product=product, user=actor)
    return {"id": product.id, "name": product.name, "is_active": False}


def void_existing_sale(*, invoice_number_or_id: str, reason: str = "") -> Dict[str, Any]:
    """Void a sale and reverse its stock, ledger, and payments atomically via sales.services.void_sale."""
    require_permission("can_access_pos")
    business = get_business()
    actor = get_actor()
    init_django()

    from sales.services import void_sale

    sale = void_sale(
        business=business,
        sale=invoice_number_or_id,
        user=actor,
        reason=reason,
    )

    return {
        "id": sale.id,
        "invoice_number": sale.invoice_number,
        "is_voided": True,
        "total_reversed": str(sale.total),
        "notes": sale.notes,
    }

