"""
agents/inventory_agent.py
==========================
Inventory Agent — validates stock availability and prepares order summary.
Does NOT create actual order in DB until user clicks "Place Order"
(handled by /order/confirm endpoint).
"""

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from agents.state import AgentState
from core.database import supabase
from observability.langfuse_client import log_agent_step

LOW_STOCK_THRESHOLD = 10


# ── Helpers ───────────────────────────────────────────────────────────────────

def _validate_stock(product_id: int, quantity: int) -> tuple[int, bool]:
    """
    Validate stock availability.
    Returns (current_stock, is_available).
    Does NOT decrement stock — that happens in /order/confirm.
    """
    if not product_id:
        raise ValueError(f"_validate_stock called with invalid product_id={product_id!r}")

    current = (
        supabase.table("products")
        .select("stock_quantity")
        .eq("id", product_id)
        .single()
        .execute()
    )
    if not current.data:
        raise ValueError(f"Product id={product_id} not found in Supabase products table")

    current_qty = int(current.data.get("stock_quantity") or 0)
    available   = current_qty >= quantity
    return current_qty, available


def _get_product_details(product_id: int) -> dict:
    """Fetch price and package_size for a product."""
    resp = (
        supabase.table("products")
        .select("price,package_size")
        .eq("id", product_id)
        .single()
        .execute()
    )
    return resp.data or {}


def _get_user_uuid(patient_id: str) -> str | None:
    """Get user UUID from patient_id."""
    resp = (
        supabase.table("users")
        .select("id")
        .eq("patient_id", patient_id.upper())
        .single()
        .execute()
    )
    return resp.data.get("id") if resp.data else None


def _log_low_stock_alert(state: AgentState, product_name: str, product_id: int, new_stock: int):
    """Write a low-stock alert to decision_ledger."""
    try:
        supabase.table("decision_ledger").insert({
            "order_id":       state.get("order_id"),
            "agent_name":     "InventoryAgent",
            "action":         "LOW_STOCK_ALERT",
            "reason":         (
                f"Stock for '{product_name}' is low at {new_stock} units "
                f"(threshold: {LOW_STOCK_THRESHOLD}). Consider re-ordering."
            ),
            "input_payload":  {"product_id": product_id, "new_stock": new_stock},
            "output_payload": {"alert": "LOW_STOCK"},
            "langfuse_trace_id": state.get("langfuse_trace_id"),
        }).execute()
    except Exception:
        pass  # ledger write failure is non-fatal


# ── Main agent node ───────────────────────────────────────────────────────────

def inventory_agent(state: AgentState) -> AgentState:
    """
    Validates stock availability and prepares order summary.
    Does NOT create the actual order — that happens in /order/confirm
    when the user clicks "Place Order".
    This ensures orders are only saved after explicit user confirmation.
    """

    if not state.get("safety_approved"):
        log_agent_step(state, "InventoryAgent", "SKIPPED",
                       {"reason": "SafetyAgent did not approve."})
        return state

    log_agent_step(state, "InventoryAgent", "START", {
        "product_id":     state.get("product_id"),
        "quantity":       state.get("extracted_quantity"),
        "payment_method": state.get("payment_method", "cash_on_delivery"),
        "multi_order":    state.get("multi_medicine_order", False),
    })

    # ── MULTI-MEDICINE ORDER PATH ─────────────────────────────────────────────
    if state.get("multi_medicine_order") and state.get("selected_products"):
        try:
            selected_products = state.get("selected_products") or []
            multi_quantities  = state.get("multi_quantities") or []
            payment_method    = state.get("payment_method") or "cash_on_delivery"
            payment_status    = "pending_cod" if payment_method == "cash_on_delivery" else "mock_paid"

            total_amount = 0.0
            line_items   = []
            validated    = True

            for i, product in enumerate(selected_products):
                qty        = multi_quantities[i] if i < len(multi_quantities) else 1
                product_id = product["id"]

                # Validate stock (don't decrement yet)
                current_qty, available = _validate_stock(product_id, qty)
                if not available:
                    validated = False
                    state["stock_reserved"] = False
                    state["final_response"] = (
                        f"❌ Cannot process order. Not enough stock for "
                        f"{product['name']} — only {current_qty} available."
                    )
                    log_agent_step(state, "InventoryAgent", "INSUFFICIENT_STOCK", {
                        "product":   product["name"],
                        "requested": qty,
                        "available": current_qty,
                    })
                    break

                details    = _get_product_details(product_id)
                unit_price = float(details.get("price", 0.0))
                line_total = round(unit_price * qty, 2)
                total_amount += line_total
                line_items.append(f"  • {product['name']} × {qty} — €{line_total:.2f}")

                # Warn if stock will be low after this order
                if current_qty - qty < LOW_STOCK_THRESHOLD:
                    _log_low_stock_alert(state, product["name"], product_id, current_qty - qty)

            if validated:
                # All stock validated — store totals, await user confirmation
                state["stock_reserved"] = True
                state["payment_status"] = payment_status
                state["total_price"]    = round(total_amount, 2)

                summary_lines = "\n".join(line_items)
                payment_line  = (
                    "\n💵 Payment: Cash on Delivery — pay when your order arrives."
                    if payment_method == "cash_on_delivery"
                    else "\n💳 Payment: Confirmed (mock online payment)."
                )
                state["final_response"] = (
                    f"✅ Your multi-item order has been placed!\n\n"
                    f"{summary_lines}\n\n"
                    f"💰 Total: €{total_amount:.2f}"
                    f"{payment_line}"
                )

                log_agent_step(state, "InventoryAgent", "MULTI_ORDER_VALIDATED", {
                    "products":     [p["name"] for p in selected_products],
                    "quantities":   multi_quantities,
                    "total_amount": total_amount,
                    "payment":      payment_method,
                })

        except Exception as e:
            state["stock_reserved"] = False
            state["final_response"] = f"❌ Error validating order: {str(e)}"
            log_agent_step(state, "InventoryAgent", "MULTI_ORDER_ERROR", {"error": str(e)})

        return state

    # ── SINGLE PRODUCT ORDER PATH ─────────────────────────────────────────────
    try:
        product_id = state.get("product_id")
        qty        = state.get("extracted_quantity", 1)

        # Validate stock (don't decrement yet)
        current_qty, available = _validate_stock(product_id, qty)

        if not available:
            state["stock_reserved"] = False
            state["final_response"] = (
                f"❌ Cannot process order — only {current_qty} unit(s) in stock."
            )
            log_agent_step(state, "InventoryAgent", "INSUFFICIENT_STOCK", {
                "product_id": product_id,
                "requested":  qty,
                "available":  current_qty,
            })
            return state

        # Fetch price + package_size
        details      = _get_product_details(product_id)
        unit_price   = float(details.get("price", 0.0))
        package_size = details.get("package_size") or None
        total        = round(unit_price * qty, 2)

        payment_method = state.get("payment_method", "cash_on_delivery")
        payment_status = "pending_cod" if payment_method == "cash_on_delivery" else "mock_paid"

        # Store pricing + package info in state — order is NOT created yet
        state["unit_price"]     = unit_price
        state["total_price"]    = total
        state["package_size"]   = package_size
        state["stock_reserved"] = True
        state["payment_status"] = payment_status

        # Build confirmation-prompt response
        payment_message = (
            "💵 Payment: Cash on Delivery — pay when your order arrives."
            if payment_method == "cash_on_delivery"
            else "💳 Payment: Confirmed (mock online payment)."
        )
        # Prepend any inline Q&A answers (supply duration, contact lens safety etc.)
        # that were computed by conversational_agent when user asked secondary questions
        # alongside their order (e.g. "how long will 20 units last? safe with contacts?")
        inline_qa_prefix = state.get("inline_qa") or ""
        if inline_qa_prefix and not inline_qa_prefix.endswith("\n\n"):
            inline_qa_prefix += "\n\n"

        state["final_response"] = (
            inline_qa_prefix
            + f"✅ Order ready! Please review and click Place Order to confirm.\n\n"
            f"📦 {qty}x {state.get('product_name')} — €{total:.2f}\n"
            f"{payment_message}"
        )
        # Clear after use
        state["inline_qa"] = None

        # Warn if stock will be low after this order
        projected_stock = current_qty - qty
        if projected_stock < LOW_STOCK_THRESHOLD:
            _log_low_stock_alert(
                state, state.get("product_name", ""), product_id, projected_stock
            )

        # Log validation to decision ledger (no order_id yet)
        try:
            supabase.table("decision_ledger").insert({
                "order_id":   None,
                "agent_name": "InventoryAgent",
                "action":     "STOCK_VALIDATED",
                "reason": (
                    f"Stock validated for {qty}x '{state.get('product_name')}'. "
                    f"Available: {current_qty}. Awaiting user confirmation."
                ),
                "input_payload": {
                    "product_id":     product_id,
                    "quantity":       qty,
                    "payment_method": payment_method,
                },
                "output_payload": {
                    "unit_price":     unit_price,
                    "total_price":    total,
                    "payment_status": payment_status,
                    "package_size":   package_size,
                },
                "langfuse_trace_id": state.get("langfuse_trace_id"),
            }).execute()
        except Exception:
            pass  # ledger write failure is non-fatal

        log_agent_step(state, "InventoryAgent", "STOCK_VALIDATED", {
            "product_id":     product_id,
            "quantity":       qty,
            "unit_price":     unit_price,
            "total_price":    total,
            "package_size":   package_size,
            "payment_status": payment_status,
        })

    except Exception as e:
        state["stock_reserved"] = False
        state["final_response"] = f"❌ Error processing order: {str(e)}"
        log_agent_step(state, "InventoryAgent", "ERROR", {"error": str(e)})

    return state