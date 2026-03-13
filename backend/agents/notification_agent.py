"""
agents/notification_agent.py
==============================
Notification Agent — fires at the end of the pipeline after every approved order.

Sends:
  1. Email order confirmation → patient
  2. Email refill reminder     → patient  (if refill_alert is set)
  3. Refill banner injected into final_response for chat UI
  4. Warehouse webhook (n8n)

Note: WhatsApp/Twilio disabled - using email instead.
"""

import sys
import json
import asyncio
import httpx
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from agents.state import AgentState
from core.database import supabase
from core.config import settings
from observability.langfuse_client import log_agent_step
# Email service (WhatsApp/Twilio disabled)
from services.email_service import (
    send_order_confirmation_email,
    send_refill_reminder_email,
)


def _get_patient_contact(patient_id: str) -> tuple[str, str, str]:
    """
    Returns (phone, email, name) for a patient.
    """
    try:
        resp = (
            supabase.table("users")
            .select("phone, email")
            .eq("patient_id", patient_id.upper())
            .single()
            .execute()
        )
        if resp.data:
            phone = resp.data.get("phone") or settings.USER_PHONE_FALLBACK
            email = resp.data.get("email") or ""
            name = email.split("@")[0] if email else "Customer"
            return phone, email, name
    except Exception as e:
        print(f"[NotificationAgent] Could not fetch patient contact: {e}")
    return settings.USER_PHONE_FALLBACK, "", "Customer"


def _log(state: AgentState, action: str, result: dict, channel: str = "email") -> None:
    try:
        supabase.table("decision_ledger").insert({
            "order_id":   state.get("order_id"),
            "agent_name": "NotificationAgent",
            "action":     action,
            "reason":     f"{channel} — success={result.get('success')}",
            "input_payload":  {
                "patient_id":   state.get("patient_id"),
                "product_name": state.get("product_name"),
            },
            "output_payload":    result,
            "langfuse_trace_id": state.get("langfuse_trace_id"),
        }).execute()
    except Exception:
        pass


async def _fire_webhook(state: AgentState) -> bool:
    if not settings.WAREHOUSE_WEBHOOK_URL:
        return False
    if getattr(settings, "MOCK_WEBHOOKS", False):
        print(f"[MOCK WEBHOOK] {settings.WAREHOUSE_WEBHOOK_URL}")
        return True
    try:
        payload = {
            "order_id":      state.get("order_id"),
            "product_name":  state.get("product_name"),
            "quantity":      state.get("extracted_quantity"),
            "patient_id":    state.get("patient_id"),
            "total_price":   state.get("total_price"),
            "payment_method": state.get("payment_method"),
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                settings.WAREHOUSE_WEBHOOK_URL,
                json=payload,
                headers={
                    "Content-Type":     "application/json",
                    "X-Webhook-Secret": getattr(settings, "WAREHOUSE_WEBHOOK_SECRET", "") or "",
                },
            )
            resp.raise_for_status()
            return True
    except Exception as e:
        print(f"[NotificationAgent] Webhook error: {e}")
        return False


def _build_chat_refill_banner(alerts: list[dict]) -> str:
    """
    Builds the refill alert banner that appears in the chat UI
    (appended to final_response).
    Shows differently based on urgency.
    """
    if not alerts:
        return ""

    lines = []
    for a in alerts[:3]:   # max 3 in the banner
        days  = a.get("days_until", 0)
        med   = a.get("medicine", "")
        date  = a.get("refill_due", "")

        if days <= 0:
            lines.append(f"🚨 *{med}* — supply may have run out!")
        elif days <= 3:
            lines.append(f"⚠️ *{med}* — only {days} day{'s' if days > 1 else ''} left (due {date})")
        else:
            lines.append(f"💊 *{med}* — refill due in {days} days ({date})")

    header = "\n\n---\n📋 *Refill Reminder"
    if len(alerts) > 1:
        header += "s"
    header += "*\n"

    body   = "\n".join(lines)
    footer = "\n\nWould you like me to reorder any of these? Just say the name."
    return header + body + footer


def notification_agent(state: AgentState) -> AgentState:
    # Only run after a successful order approval
    if state.get("order_status") != "approved":
        return state

    patient_id     = state.get("patient_id", "")
    product_name   = state.get("product_name") or "your medicine"
    quantity       = state.get("extracted_quantity") or 1
    total_price    = state.get("total_price") or 0.0
    order_id       = state.get("order_id") or ""
    payment_method = state.get("payment_method") or "cash_on_delivery"
    stock_level    = state.get("new_stock_level")
    rx_required    = state.get("prescription_required", False)

    log_agent_step(state=state, agent="NotificationAgent", action="START", details={
        "patient_id":   patient_id,
        "product_name": product_name,
        "stock_level":  stock_level,
        "refill_alert": state.get("refill_alert"),
    })

    phone, email, name = _get_patient_contact(patient_id)

    # NOTE: Order confirmation email is now sent from orders.py when user clicks "Place Order"
    # So we only send refill reminder emails here (not order confirmation)
    email_sent = False

    # ── 1. Refill reminder → patient (email + chat banner) ─────────────────
    notification_channel = "email"
    if state.get("refill_alert"):
        refill_medicine = state.get("refill_medicine") or product_name
        refill_due_date = state.get("refill_due_date") or "soon"

        # Calculate days_left
        days_left = 7
        try:
            from datetime import date, datetime
            due       = datetime.strptime(refill_due_date, "%Y-%m-%d").date()
            days_left = (due - date.today()).days
        except Exception:
            pass

        # Email to patient
        if email and settings.ENABLE_EMAIL_NOTIFICATIONS:
            refill_email = send_refill_reminder_email(
                to_email=email,
                patient_name=name,
                medicine_name=refill_medicine,
                days_left=days_left,
                due_date=refill_due_date,
            )
            _log(state, "REFILL_REMINDER_EMAIL", refill_email, "email")

        # Chat UI banner — inject into final_response
        # Build a richer alert list from state refill_patterns if available
        refill_patterns = state.get("refill_patterns") or []
        if refill_patterns:
            alert_items = [
                {
                    "medicine":   p.get("medicine_name") or p.get("medicine", ""),
                    "days_until": p.get("days_until_refill", days_left),
                    "refill_due": p.get("predicted_refill_date") or p.get("refill_due", refill_due_date),
                }
                for p in refill_patterns
                if p.get("days_until_refill", 999) <= 30
            ]
        else:
            alert_items = [{
                "medicine":   refill_medicine,
                "days_until": days_left,
                "refill_due": refill_due_date,
            }]

        banner = _build_chat_refill_banner(alert_items)
        if banner:
            state["final_response"] = (state.get("final_response") or "") + banner

        state["notification_sent"]    = True
        state["notification_channel"] = notification_channel

    # ── 3. Warehouse webhook ──────────────────────────────────────────────────
    webhook_ok = False
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future     = pool.submit(asyncio.run, _fire_webhook(state))
                webhook_ok = future.result(timeout=12)
        else:
            webhook_ok = loop.run_until_complete(_fire_webhook(state))
    except Exception as e:
        print(f"[NotificationAgent] Webhook dispatch error: {e}")

    state["webhook_triggered"]  = webhook_ok
    state["notification_sent"]  = True
    state["notification_channel"] = notification_channel

    log_agent_step(state=state, agent="NotificationAgent", action="COMPLETE", details={
        "webhook_ok":      webhook_ok,
        "patient_email_sent": email_sent,
        "stock_level":     stock_level,
    })

    return state

