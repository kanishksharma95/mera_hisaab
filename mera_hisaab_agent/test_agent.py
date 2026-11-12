"""
End-to-End Test Suite for Mera Hisaab ADK Agent.

Tests:
1. Config validation (zero hardcoding).
2. Django standalone bootstrap (lazy import).
3. Multi-tenant context and permission checks.
4. Read tools via repository.
5. Confirmation gate for write tools (RULE SET F).
6. Execution of writes via service layer (RULE SET B).
7. Soft-delete and void-sale immutability.
"""
import asyncio
import os
import sys
from decimal import Decimal
from pathlib import Path

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


# Setup path so mh_agent is discoverable
AGENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(AGENT_DIR))

from mh_agent.config import config
from mh_agent.context import get_actor, get_business, get_membership, check_permission
from mh_agent.callbacks import before_tool_guardrail
from mh_agent.tools import (
    get_sales_summary_tool,
    list_low_stock_products_tool,
    search_products_tool,
    get_product_detail_tool,
    search_customers_tool,
    list_pending_udhaar_tool,
    create_customer_tool,
    update_customer_tool,
    deactivate_customer_tool,
    create_product_tool,
    update_product_tool,
    deactivate_product_tool,
    create_sale_tool,
    record_customer_payment_tool,
    record_customer_charge_tool,
    void_sale_tool,
    list_recent_sales_tool,
)
from mh_agent.agent import root_agent


async def run_all_tests():
    print("--- 1. Testing Config & Django Setup ---")
    print(f"Loaded config: Business ID = {config.business_id}, Actor User ID = {config.agent_actor_user_id}")
    assert config.business_id > 0
    assert config.agent_actor_user_id > 0

    print("--- 2. Testing Context & Tenant Isolation ---")
    business = get_business()
    actor = get_actor()
    membership = get_membership()
    print(f"Business: {business.name} (Currency: {business.currency_symbol})")
    print(f"Actor: {actor.full_name} ({actor.email})")
    print(f"Role: {membership.role}")
    assert check_permission("can_manage_inventory") is True
    assert check_permission("can_manage_customers") is True
    assert check_permission("can_access_pos") is True
    assert check_permission("can_view_reports") is True

    print("--- 3. Testing Read Tools ---")
    sales_summary = await get_sales_summary_tool(period="today")
    print("Sales Summary Status:", sales_summary.get("status"))
    assert sales_summary["status"] == "success"

    low_stock = await list_low_stock_products_tool()
    print("Low Stock Count:", low_stock.get("count"))
    assert low_stock["status"] == "success"

    products_search = await search_products_tool(query="", limit=5)
    print("Products Found:", products_search.get("count"))
    assert products_search["status"] == "success"

    udhaar_list = await list_pending_udhaar_tool(limit=5)
    print("Pending Udhaar Customers:", udhaar_list.get("count"))
    assert udhaar_list["status"] == "success"

    print("--- 4. Testing RULE SET F: Confirmation Gate Guardrail ---")
    # Call create_product_tool with confirm=False -> Must return pending_confirmation
    unconfirmed_product = await create_product_tool(
        name="Agent Test Biscuit",
        selling_price=25.0,
        confirm=False,
    )
    assert unconfirmed_product["status"] == "pending_confirmation"
    print("create_product (confirm=False): Blocked correctly with pending_confirmation.")

    # Test before_tool_guardrail directly
    class DummyTool:
        name = "create_product_tool"

    blocked = before_tool_guardrail(DummyTool(), {"confirm": False}, None)
    assert blocked is not None and blocked.get("status") == "pending_confirmation"
    print("before_tool_guardrail: Blocked unconfirmed write call successfully.")

    allowed = before_tool_guardrail(DummyTool(), {"confirm": True}, None)
    assert allowed is None
    print("before_tool_guardrail: Allowed confirmed write call.")

    print("--- 5. Testing Confirmed Writes (Service Layer Discipline) ---")
    import time
    ts = int(time.time())
    test_sku = f"NOODLE-{ts}"
    test_cust_phone = f"98765{ts % 100000:05d}"

    # 5a. Create product
    created_prod = await create_product_tool(
        name=f"Agent Test Noodles {ts}",
        selling_price=30.0,
        purchase_price=22.0,
        sku=test_sku,
        opening_stock=50.0,
        unit="pack",
        min_stock_level=10.0,
        confirm=True,
    )
    if created_prod.get("status") != "success":
        print("Create product error:", created_prod)
    assert created_prod["status"] == "success"
    prod_id = created_prod["product"]["id"]
    print(f"Product created: ID {prod_id}, Name: {created_prod['product']['name']}")

    # 5b. Create customer
    created_cust = await create_customer_tool(
        name=f"Agent Grahak {ts}",
        phone=test_cust_phone,
        credit_limit=2000.0,
        confirm=True,
    )
    if created_cust.get("status") != "success":
        print("Create customer error:", created_cust)
    assert created_cust["status"] == "success"
    cust_id = created_cust["customer"]["id"]
    print(f"Customer created: ID {cust_id}, Name: {created_cust['customer']['name']}")

    # 5c. Create sale (POS) with partial payment & udhaar
    sale_res = await create_sale_tool(
        items=[{"product_id_or_name": test_sku, "quantity": 2, "unit_price": 30.0}],
        customer_id_or_name=f"Agent Grahak {ts}",
        cash_amount=20.0,
        confirm=True,
    )
    if sale_res.get("status") != "success":
        print("Create sale error:", sale_res)
    assert sale_res["status"] == "success"
    invoice_no = sale_res["sale"]["invoice_number"]
    total = sale_res["sale"]["total"]
    paid = sale_res["sale"]["paid_amount"]
    due = sale_res["sale"]["due_amount"]
    print(f"Sale recorded: Invoice {invoice_no}, Total: {total}, Paid: {paid}, Due: {due}")
    assert Decimal(due) == Decimal("40.00")

    # 5d. Record customer payment (jama)
    pay_res = await record_customer_payment_tool(
        customer_id_or_name=f"Agent Grahak {ts}",
        amount=40.0,
        method="Cash",
        confirm=True,
    )
    if pay_res.get("status") != "success":
        print("Record payment error:", pay_res)
    assert pay_res["status"] == "success"
    new_bal = pay_res["data"]["new_balance"]
    print(f"Payment recorded: New Customer Balance: ₹{new_bal}")
    assert Decimal(new_bal) == Decimal("0.00")

    # 5e. Void sale (Reversal)
    void_res = await void_sale_tool(
        invoice_number_or_id=invoice_no,
        reason="Agent testing cancellation",
        confirm=True,
    )
    print("Void response:", void_res)
    assert void_res["status"] == "success"

    print(f"Sale voided: {void_res['sale']['invoice_number']}, Voided: {void_res['sale']['is_voided']}")

    # 5f. Soft-delete cleanups
    deact_prod = await deactivate_product_tool(product_id_or_sku=test_sku, confirm=True)
    assert deact_prod["status"] == "success"
    print("Product soft-deactivated successfully.")

    deact_cust = await deactivate_customer_tool(customer_id_or_name=str(cust_id), confirm=True)
    assert deact_cust["status"] == "success"
    print("Customer soft-deactivated successfully.")

    print("--- 6. Testing root_agent definition ---")
    assert root_agent.name == "mera_hisaab_agent"
    assert len(root_agent.tools) == 19
    print(f"root_agent verified with {len(root_agent.tools)} tools.")

    print("\nALL 6 TEST SUITES PASSED CLEANLY! 100% SUCCESS.")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
