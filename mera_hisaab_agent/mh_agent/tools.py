"""
ADK Tool functions for the Mera Hisaab Agent.

Provides:
- Read tools: query sales, inventory, udhaar ledger, customers.
- Write tools: create sale (POS), udhaar payments, charges, product CRUD, customer CRUD, void sale.
- Every write tool enforces the `confirm: bool = False` pattern.
"""
from typing import Any, Dict, List, Optional
from asgiref.sync import sync_to_async

from . import actions, repository


# ---------------------------------------------------------
# Read Tools
# ---------------------------------------------------------

async def get_sales_summary_tool(period: str = "today") -> Dict[str, Any]:
    """Get the shop's sales summary and totals.
    
    Args:
        period: Time window - 'today', 'week', 'month', or 'all'.
    """
    try:
        data = await sync_to_async(repository.get_sales_summary)(period=period)
        return {"status": "success", "data": data}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


async def list_low_stock_products_tool() -> Dict[str, Any]:
    """List all products in the shop that have reached or dropped below their minimum stock alert level."""
    try:
        data = await sync_to_async(repository.list_low_stock_products)()
        return {"status": "success", "count": len(data), "products": data}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


async def search_products_tool(query: str = "", limit: int = 20) -> Dict[str, Any]:
    """Search products by name, SKU, or barcode.
    
    Args:
        query: Search term (e.g. 'Maggi', 'Atta', 'Soap', or SKU).
        limit: Max products to return.
    """
    try:
        data = await sync_to_async(repository.search_products)(query=query, limit=limit)
        return {"status": "success", "count": len(data), "products": data}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


async def get_product_detail_tool(product_id_or_sku: str) -> Dict[str, Any]:
    """Get complete details of a specific product (stock, pricing, unit, category).
    
    Args:
        product_id_or_sku: Product ID, exact SKU, or name.
    """
    try:
        data = await sync_to_async(repository.get_product_detail)(product_id_or_sku=product_id_or_sku)
        if not data:
            return {"status": "not_found", "message": f"Product '{product_id_or_sku}' not found."}
        return {"status": "success", "product": data}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


async def search_customers_tool(query: str = "", limit: int = 20) -> Dict[str, Any]:
    """Search registered customers by name or phone number.
    
    Args:
        query: Customer name or phone number snippet.
        limit: Max results.
    """
    try:
        data = await sync_to_async(repository.search_customers)(query=query, limit=limit)
        return {"status": "success", "count": len(data), "customers": data}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


async def list_pending_udhaar_tool(limit: int = 20) -> Dict[str, Any]:
    """List customers with outstanding udhaar/credit balance, sorted highest first."""
    try:
        data = await sync_to_async(repository.list_pending_udhaar)(limit=limit)
        return {"status": "success", "count": len(data), "customers": data}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


async def get_customer_detail_tool(customer_id_or_name: str) -> Dict[str, Any]:
    """Get detailed customer info including recent udhaar ledger entries and WhatsApp reminder link.
    
    Args:
        customer_id_or_name: Customer ID, phone, or name.
    """
    try:
        data = await sync_to_async(repository.get_customer_detail)(customer_id_or_name=customer_id_or_name)
        if not data:
            return {"status": "not_found", "message": f"Customer '{customer_id_or_name}' not found."}
        return {"status": "success", "customer": data}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


async def list_recent_sales_tool(limit: int = 10) -> Dict[str, Any]:
    """List recent invoices/sales."""
    try:
        data = await sync_to_async(repository.list_recent_sales)(limit=limit)
        return {"status": "success", "count": len(data), "sales": data}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


async def get_sale_detail_tool(invoice_number_or_id: str) -> Dict[str, Any]:
    """Get full details of a specific sale invoice (items, payments, udhaar).
    
    Args:
        invoice_number_or_id: Invoice number (e.g. 'MH-2026-000001') or Sale ID.
    """
    try:
        data = await sync_to_async(repository.get_sale_detail)(invoice_number_or_id=invoice_number_or_id)
        if not data:
            return {"status": "not_found", "message": f"Sale '{invoice_number_or_id}' not found."}
        return {"status": "success", "sale": data}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# ---------------------------------------------------------
# Write Tools (RULE SET F: require confirm: bool = False)
# ---------------------------------------------------------

async def create_sale_tool(
    items: List[Dict[str, Any]],
    customer_id_or_name: str = "",
    cash_amount: float = 0.0,
    upi_amount: float = 0.0,
    order_discount: float = 0.0,
    notes: str = "",
    confirm: bool = False,
) -> Dict[str, Any]:
    """Create a new sale invoice at POS.
    
    Decrements product inventory, records payments, and logs remaining balance to customer's udhaar ledger.
    
    Args:
        items: List of items, e.g. [{"product_id_or_name": "Milk", "quantity": 2, "unit_price": 30.0}]
        customer_id_or_name: Customer name/ID (Required if there is unpaid balance / udhaar).
        cash_amount: Cash payment received.
        upi_amount: UPI payment received.
        order_discount: Bill discount amount.
        notes: Invoice notes.
        confirm: Must be True to execute. If False, returns summary for user confirmation.
    """
    if not confirm:
        return {
            "status": "pending_confirmation",
            "action": "create_sale",
            "message": "Please review the sale details below and confirm to record this transaction.",
            "details": {
                "items": items,
                "customer": customer_id_or_name or "Walk-in (Cash)",
                "cash_paid": cash_amount,
                "upi_paid": upi_amount,
                "discount": order_discount,
            },
        }

    try:
        result = await sync_to_async(actions.record_sale)(
            items=items,
            customer_id_or_name=customer_id_or_name or None,
            cash_amount=cash_amount,
            upi_amount=upi_amount,
            order_discount=order_discount,
            notes=notes,
        )
        return {"status": "success", "message": "Sale recorded successfully.", "sale": result}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


async def record_customer_payment_tool(
    customer_id_or_name: str,
    amount: float,
    method: str = "Cash",
    description: str = "",
    confirm: bool = False,
) -> Dict[str, Any]:
    """Record payment received from a customer (jama / deposit) to decrease their udhaar.
    
    Args:
        customer_id_or_name: Customer name, phone, or ID.
        amount: Payment amount received (positive number).
        method: Payment method ('Cash', 'UPI', etc.).
        description: Note or reference.
        confirm: Must be True to execute. If False, returns summary for confirmation.
    """
    if not confirm:
        return {
            "status": "pending_confirmation",
            "action": "record_customer_payment",
            "message": f"Confirm receiving payment of ₹{amount:.2f} ({method}) from customer '{customer_id_or_name}'?",
            "details": {
                "customer": customer_id_or_name,
                "amount": amount,
                "method": method,
                "description": description,
            },
        }

    try:
        result = await sync_to_async(actions.record_customer_payment)(
            customer_id_or_name=customer_id_or_name,
            amount=amount,
            method=method,
            description=description,
        )
        return {"status": "success", "message": "Payment recorded successfully in ledger.", "data": result}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


async def record_customer_charge_tool(
    customer_id_or_name: str,
    amount: float,
    description: str = "",
    confirm: bool = False,
) -> Dict[str, Any]:
    """Record manual udhaar / debit charge for a customer (increases what customer owes).
    
    Args:
        customer_id_or_name: Customer name, phone, or ID.
        amount: Udhaar amount (positive number).
        description: Reason for charge (e.g. 'Old balance', 'Delivery fee').
        confirm: Must be True to execute. If False, returns summary for confirmation.
    """
    if not confirm:
        return {
            "status": "pending_confirmation",
            "action": "record_customer_charge",
            "message": f"Confirm adding udhaar charge of ₹{amount:.2f} to customer '{customer_id_or_name}'?",
            "details": {
                "customer": customer_id_or_name,
                "amount": amount,
                "description": description,
            },
        }

    try:
        result = await sync_to_async(actions.record_customer_charge)(
            customer_id_or_name=customer_id_or_name,
            amount=amount,
            description=description,
        )
        return {"status": "success", "message": "Udhaar charge added successfully to ledger.", "data": result}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


async def create_customer_tool(
    name: str,
    phone: str = "",
    email: str = "",
    address: str = "",
    credit_limit: float = 0.0,
    notes: str = "",
    confirm: bool = False,
) -> Dict[str, Any]:
    """Add a new customer to the shop khata.
    
    Args:
        name: Full customer name (Required).
        phone: Phone number (10 digits).
        email: Email address.
        address: Delivery / home address.
        credit_limit: Max allowed credit (0 = no limit).
        notes: Customer notes.
        confirm: Must be True to execute. If False, returns summary for confirmation.
    """
    if not confirm:
        return {
            "status": "pending_confirmation",
            "action": "create_customer",
            "message": f"Confirm creating customer profile '{name}' (Phone: {phone or 'N/A'})?",
            "details": {
                "name": name,
                "phone": phone,
                "email": email,
                "credit_limit": credit_limit,
            },
        }

    try:
        result = await sync_to_async(actions.create_new_customer)(
            name=name,
            phone=phone,
            email=email,
            address=address,
            credit_limit=credit_limit,
            notes=notes,
        )
        return {"status": "success", "message": "Customer profile created successfully.", "customer": result}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


async def update_customer_tool(
    customer_id_or_name: str,
    name: str = "",
    phone: str = "",
    email: str = "",
    address: str = "",
    credit_limit: float = -1.0,
    notes: str = "",
    confirm: bool = False,
) -> Dict[str, Any]:
    """Update contact or profile information of an existing customer.
    
    Args:
        customer_id_or_name: Customer ID, phone, or name.
        name: New name (leave empty to keep unchanged).
        phone: New phone number.
        email: New email.
        address: New address.
        credit_limit: New credit limit (-1 to keep unchanged).
        notes: New notes.
        confirm: Must be True to execute.
    """
    if not confirm:
        return {
            "status": "pending_confirmation",
            "action": "update_customer",
            "message": f"Confirm updating customer profile for '{customer_id_or_name}'?",
            "details": {
                "customer": customer_id_or_name,
                "name": name or None,
                "phone": phone or None,
                "credit_limit": credit_limit if credit_limit >= 0 else None,
            },
        }

    try:
        result = await sync_to_async(actions.update_existing_customer)(
            customer_id_or_name=customer_id_or_name,
            name=name or None,
            phone=phone or None,
            email=email or None,
            address=address or None,
            credit_limit=credit_limit if credit_limit >= 0 else None,
            notes=notes or None,
        )
        return {"status": "success", "message": "Customer updated successfully.", "customer": result}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


async def deactivate_customer_tool(
    customer_id_or_name: str,
    confirm: bool = False,
) -> Dict[str, Any]:
    """Soft-delete / deactivate a customer (marks inactive, preserving historical ledger).
    
    Args:
        customer_id_or_name: Customer ID, phone, or name.
        confirm: Must be True to execute.
    """
    if not confirm:
        return {
            "status": "pending_confirmation",
            "action": "deactivate_customer",
            "message": f"Confirm deactivating customer '{customer_id_or_name}'? (Historical ledger remains safe).",
            "details": {"customer": customer_id_or_name},
        }

    try:
        result = await sync_to_async(actions.deactivate_existing_customer)(
            customer_id_or_name=customer_id_or_name
        )
        return {"status": "success", "message": "Customer deactivated successfully.", "customer": result}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


async def create_product_tool(
    name: str,
    selling_price: float,
    purchase_price: float = 0.0,
    sku: str = "",
    barcode: str = "",
    category_name: str = "",
    brand: str = "",
    unit: str = "pcs",
    opening_stock: float = 0.0,
    min_stock_level: float = 0.0,
    confirm: bool = False,
) -> Dict[str, Any]:
    """Add a new product to shop inventory.
    
    Args:
        name: Product name (e.g. 'Parle-G 100g', 'Basmati Rice 1kg').
        selling_price: Selling retail price.
        purchase_price: Cost/purchase price.
        sku: Unique SKU code (optional).
        barcode: Barcode value (optional).
        category_name: Category (e.g. 'Biscuits', 'Grains').
        brand: Brand name.
        unit: Unit of measure ('pcs', 'kg', 'litre').
        opening_stock: Initial stock on hand.
        min_stock_level: Stock alert threshold.
        confirm: Must be True to execute.
    """
    if not confirm:
        return {
            "status": "pending_confirmation",
            "action": "create_product",
            "message": f"Confirm adding product '{name}' (Price: ₹{selling_price:.2f}, Opening Stock: {opening_stock} {unit})?",
            "details": {
                "name": name,
                "selling_price": selling_price,
                "purchase_price": purchase_price,
                "opening_stock": opening_stock,
                "unit": unit,
                "category": category_name,
            },
        }

    try:
        result = await sync_to_async(actions.create_new_product)(
            name=name,
            selling_price=selling_price,
            purchase_price=purchase_price,
            sku=sku,
            barcode=barcode,
            category_name=category_name or None,
            brand=brand,
            unit=unit,
            opening_stock=opening_stock,
            min_stock_level=min_stock_level,
        )
        return {"status": "success", "message": "Product created successfully.", "product": result}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


async def update_product_tool(
    product_id_or_sku: str,
    name: str = "",
    selling_price: float = -1.0,
    purchase_price: float = -1.0,
    sku: str = "",
    min_stock_level: float = -1.0,
    unit: str = "",
    confirm: bool = False,
) -> Dict[str, Any]:
    """Update catalog information of an existing product (current stock is changed only via sales/adjustments).
    
    Args:
        product_id_or_sku: Product ID or SKU.
        name: New name (leave empty to keep unchanged).
        selling_price: New selling price (-1 to keep unchanged).
        purchase_price: New cost price (-1 to keep unchanged).
        sku: New SKU.
        min_stock_level: New low-stock alert level (-1 to keep unchanged).
        unit: New unit.
        confirm: Must be True to execute.
    """
    if not confirm:
        return {
            "status": "pending_confirmation",
            "action": "update_product",
            "message": f"Confirm updating product '{product_id_or_sku}'?",
            "details": {
                "product": product_id_or_sku,
                "name": name or None,
                "selling_price": selling_price if selling_price >= 0 else None,
                "purchase_price": purchase_price if purchase_price >= 0 else None,
            },
        }

    try:
        result = await sync_to_async(actions.update_existing_product)(
            product_id_or_sku=product_id_or_sku,
            name=name or None,
            selling_price=selling_price if selling_price >= 0 else None,
            purchase_price=purchase_price if purchase_price >= 0 else None,
            sku=sku or None,
            min_stock_level=min_stock_level if min_stock_level >= 0 else None,
            unit=unit or None,
        )
        return {"status": "success", "message": "Product updated successfully.", "product": result}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


async def deactivate_product_tool(
    product_id_or_sku: str,
    confirm: bool = False,
) -> Dict[str, Any]:
    """Soft-delete / deactivate a product from the active catalog.
    
    Args:
        product_id_or_sku: Product ID or SKU.
        confirm: Must be True to execute.
    """
    if not confirm:
        return {
            "status": "pending_confirmation",
            "action": "deactivate_product",
            "message": f"Confirm deactivating product '{product_id_or_sku}'? (Stock movement history remains safe).",
            "details": {"product": product_id_or_sku},
        }

    try:
        result = await sync_to_async(actions.deactivate_existing_product)(
            product_id_or_sku=product_id_or_sku
        )
        return {"status": "success", "message": "Product deactivated successfully.", "product": result}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


async def void_sale_tool(
    invoice_number_or_id: str,
    reason: str = "",
    confirm: bool = False,
) -> Dict[str, Any]:
    """Void / cancel a sale invoice.
    
    Atomically returns sold inventory back to stock, creates refund payment records for received amounts,
    and reverses customer credit/udhaar. Original invoice remains for auditing.
    
    Args:
        invoice_number_or_id: Invoice number (e.g. 'MH-2026-000001') or Sale ID.
        reason: Cancellation reason (e.g. 'Customer returned items', 'Entry mistake').
        confirm: Must be True to execute.
    """
    if not confirm:
        return {
            "status": "pending_confirmation",
            "action": "void_sale",
            "message": f"Confirm VOIDING sale '{invoice_number_or_id}'? This will return stock, refund payments, and reverse customer udhaar.",
            "details": {
                "invoice": invoice_number_or_id,
                "reason": reason or "Customer cancelled",
            },
        }

    try:
        result = await sync_to_async(actions.void_existing_sale)(
            invoice_number_or_id=invoice_number_or_id,
            reason=reason,
        )
        return {"status": "success", "message": "Sale voided and reversed successfully.", "sale": result}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


ALL_TOOLS = [
    # Reads
    get_sales_summary_tool,
    list_low_stock_products_tool,
    search_products_tool,
    get_product_detail_tool,
    search_customers_tool,
    list_pending_udhaar_tool,
    get_customer_detail_tool,
    list_recent_sales_tool,
    get_sale_detail_tool,
    # Writes
    create_sale_tool,
    record_customer_payment_tool,
    record_customer_charge_tool,
    create_customer_tool,
    update_customer_tool,
    deactivate_customer_tool,
    create_product_tool,
    update_product_tool,
    deactivate_product_tool,
    void_sale_tool,
]

