"""
routers/webhooks.py
====================
Warehouse webhook receiver + Email notification endpoints.
WhatsApp/Twilio has been disabled - using email instead.
"""

import sys
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from core.database import supabase
from core.config import settings

router = APIRouter(tags=["Webhooks"])


# ── Warehouse webhook receiver ────────────────────────────────────────────────

class WarehouseWebhookIn(BaseModel):
    order_id:      Optional[str] = None
    product_name:  Optional[str] = None
    quantity:      Optional[int] = None
    patient_id:    Optional[str] = None
    total_price:   Optional[float] = None
    payment_method: Optional[str] = None


@router.post("/webhook/warehouse")
async def warehouse_webhook(body: WarehouseWebhookIn):
    """Receives order notifications from the notification agent."""
    try:
        supabase.table("decision_ledger").insert({
            "agent_name":     "WarehouseWebhook",
            "action":         "WEBHOOK_RECEIVED",
            "reason":         f"Warehouse received order for {body.product_name}",
            "input_payload":  body.dict(),
            "output_payload": {"status": "received"},
        }).execute()
    except Exception:
        pass
    return {"status": "received", "order_id": body.order_id}


# ── Email test endpoint (dev only) ────────────────────────────────────────────

class EmailTestIn(BaseModel):
    to:      str    # email address
    type:    str = "order"   # order | refill


@router.post("/test/email", tags=["Dev & Testing"])
async def test_email(body: EmailTestIn):
    """
    DEV ONLY - Send a test email to verify email service integration.
    """
    from services.email_service import (
        send_order_confirmation_email,
        send_refill_reminder_email,
    )

    print(f"\n{'='*60}")
    print(f"[Email TEST] type={body.type} to={body.to}")
    print(f"  ENABLE_EMAIL_NOTIFICATIONS = {settings.ENABLE_EMAIL_NOTIFICATIONS}")
    print(f"  EMAIL_FROM = {settings.EMAIL_FROM}")
    print(f"{'='*60}\n")

    result = {}

    if body.type == "order":
        result = send_order_confirmation_email(
            to_email=body.to,
            patient_name="Test Patient",
            medicine_name="Ramipril 10mg",
            quantity=2,
            total_price=24.50,
            order_id="TEST-ORDER-001",
            payment_method="cash_on_delivery",
        )
    elif body.type == "refill":
        result = send_refill_reminder_email(
            to_email=body.to,
            patient_name="Test Patient",
            medicine_name="Ramipril 10mg",
            days_left=3,
            due_date="2026-03-05",
        )

    return {
        "sent":       result.get("success"),
        "message_id": result.get("message_id"),
        "error":      result.get("error"),
        "channel":    "email",
        "to":         body.to,
    }
