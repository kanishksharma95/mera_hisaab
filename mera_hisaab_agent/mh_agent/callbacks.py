"""
Guardrail callbacks for the Mera Hisaab ADK Agent.

Enforces:
1. RULE SET F: Defense-in-depth confirmation gate. Any mutating/write tool call
   lacking confirm=True is blocked before execution and returns an explicit
   confirmation prompt.
2. Capability permission checks before tool invocation.
"""
from typing import Any, Dict, Optional
from google.adk.agents.context import Context
from google.adk.tools.base_tool import BaseTool

from .context import check_permission

WRITE_TOOLS = {
    "create_sale_tool": "can_access_pos",
    "void_sale_tool": "can_access_pos",
    "record_customer_payment_tool": "can_manage_customers",
    "record_customer_charge_tool": "can_manage_customers",
    "create_customer_tool": "can_manage_customers",
    "update_customer_tool": "can_manage_customers",
    "deactivate_customer_tool": "can_manage_customers",
    "create_product_tool": "can_manage_inventory",
    "update_product_tool": "can_manage_inventory",
    "deactivate_product_tool": "can_manage_inventory",
}

READ_TOOLS = {
    "get_sales_summary_tool": "can_view_reports",
    "list_low_stock_products_tool": "can_manage_inventory",
    "search_products_tool": None,
    "get_product_detail_tool": None,
    "search_customers_tool": "can_manage_customers",
    "list_pending_udhaar_tool": "can_manage_customers",
    "get_customer_detail_tool": "can_manage_customers",
    "list_recent_sales_tool": "can_access_pos",
    "get_sale_detail_tool": "can_access_pos",
}


def before_tool_guardrail(
    tool: BaseTool,
    tool_args: Dict[str, Any],
    tool_context: Context,
) -> Optional[Dict[str, Any]]:
    """Enforces write confirmation and permission check before tool execution."""
    tool_name = getattr(tool, "name", "")

    # 1. Permission check
    required_perm = WRITE_TOOLS.get(tool_name) or READ_TOOLS.get(tool_name)
    if required_perm:
        if not check_permission(required_perm):
            return {
                "status": "forbidden",
                "error": f"Permission denied: Actor role does not have '{required_perm}' in this shop.",
            }

    # 2. Confirmation check for write tools
    if tool_name in WRITE_TOOLS:
        confirm = bool(tool_args.get("confirm", False))
        if not confirm:
            return {
                "status": "pending_confirmation",
                "message": (
                    f"Defense-in-depth guardrail: The write action '{tool_name}' requires explicit confirmation. "
                    f"Please review the planned action details with the user and execute with confirm=True only after their consent."
                ),
                "planned_parameters": tool_args,
            }

    # Return None to let the tool execute normally
    return None

