"""
services/twilio_service.py
===========================
Twilio WhatsApp messaging for PharmAI.

SANDBOX SETUP (5 min):
  1. Go to https://console.twilio.com
  2. Messaging → Try it out → Send a WhatsApp message
  3. Your phone WhatsApp → send "join <sandbox-word>" to +14155238886
  4. Done — you will now receive messages from the sandbox

.env required:
  TWILIO_ACCOUNT_SID=ACxxxx
  TWILIO_AUTH_TOKEN=xxxx
  TWILIO_WHATSAPP_FROM=whatsapp:+14155238886   ← sandbox number (already default)
  ADMIN_PHONE_NUMBER=+91xxxxxxxxxx             ← your WhatsApp number (no prefix)
  USER_PHONE_FALLBACK=+91xxxxxxxxxx            ← patient fallback
  ENABLE_WHATSAPP=True
"""

import sys
from pathlib import Path
from datetime import datetime

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from core.config import settings


# ── Twilio client (lazy) ──────────────────────────────────────────────────────

def _client():
    from twilio.rest import Client
    return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


def _to_wa(number: str) -> str:
    """Add whatsapp: prefix if missing."""
    number = (number or "").strip()
    if not number:
        return ""
    return number if number.startswith("whatsapp:") else f"whatsapp:{number}"


# ── Core send ─────────────────────────────────────────────────────────────────

def _send(to: str, body: str) -> dict:
    """
    Send WhatsApp message. Never raises.
    Returns {"success": bool, "sid": str, "mock": bool, "error": str}
    """
    # ── MOCK mode (credentials not set) ──────────────────────────────────────
    if not settings.twilio_enabled:
        wa_from_display = getattr(settings, "TWILIO_WHATSAPP_FROM", None) or getattr(settings, "TWILIO_FROM_NUMBER", "NOT SET")
        print(
            f"\n{'─'*50}\n"
            f"[WhatsApp MOCK]\n"
            f"To  : {_to_wa(to)}\n"
            f"From: {wa_from_display}\n"
            f"Body:\n{body}\n"
            f"{'─'*50}\n"
        )
        return {"success": True, "sid": "MOCK_SID", "mock": True}

    to_wa   = _to_wa(to)
    # Support both field names — TWILIO_WHATSAPP_FROM (new) or TWILIO_FROM_NUMBER (old)
    from_wa = (
        getattr(settings, "TWILIO_WHATSAPP_FROM", None)
        or getattr(settings, "TWILIO_FROM_NUMBER", "")
    )

    # Validate numbers
    if not to_wa:
        err = f"[WhatsApp] Invalid recipient number: '{to}'"
        print(err)
        return {"success": False, "error": err, "mock": False}

    if not from_wa.startswith("whatsapp:"):
        err = f"[WhatsApp] TWILIO_WHATSAPP_FROM must start with 'whatsapp:' — got: '{from_wa}'"
        print(err)
        return {"success": False, "error": err, "mock": False}

    # ── Send ─────────────────────────────────────────────────────────────────
    try:
        msg = _client().messages.create(
            to=   to_wa,
            from_=from_wa,
            body= body,
        )
        print(f"[WhatsApp] ✅ Sent to {to_wa} | SID: {msg.sid} | Status: {msg.status}")
        return {"success": True, "sid": msg.sid, "mock": False}
    except Exception as e:
        print(f"[WhatsApp] ❌ Failed to {to_wa}: {e}")
        return {"success": False, "error": str(e), "mock": False}


def _send_admin(body: str) -> dict:
    """Send WhatsApp to the admin number from .env."""
    if not settings.ADMIN_PHONE_NUMBER:
        print("[WhatsApp] ADMIN_PHONE_NUMBER not set in .env — skipping admin alert")
        return {"success": False, "error": "ADMIN_PHONE_NUMBER not configured"}
    return _send(settings.ADMIN_PHONE_NUMBER, body)


# ══════════════════════════════════════════════════════════════════════════════
# USER MESSAGES
# ══════════════════════════════════════════════════════════════════════════════

def send_order_confirmation(
    patient_phone:  str,
    patient_name:   str,
    medicine_name:  str,
    quantity:       int,
    total_price:    float,
    order_id:       str,
    payment_method: str = "cash_on_delivery",
) -> dict:
    payment_label = (
        "Cash on Delivery 💵" if payment_method == "cash_on_delivery"
        else "Online Payment ✅"
    )
    short_id = str(order_id)[:8].upper()

    body = (
        f"*PharmAI — Order Confirmed* ✅\n\n"
        f"Hi {patient_name}! Your order has been placed successfully.\n\n"
        f"📦 *{medicine_name}* × {quantity}\n"
        f"💰 Total: *€{total_price:.2f}*\n"
        f"💳 {payment_label}\n"
        f"🔖 Order: #{short_id}\n\n"
        f"We'll prepare your order shortly. Thank you! 🙏\n"
        f"— PharmAI Pharmacy 🏥"
    )
    return _send(patient_phone, body)


def send_refill_reminder(
    patient_phone: str,
    patient_name:  str,
    medicine_name: str,
    days_left:     int,
    due_date:      str,
) -> dict:
    if days_left <= 0:
        urgency = "⚠️ *TODAY* — you may have already run out!"
        emoji   = "🚨"
    elif days_left <= 2:
        urgency = f"in *{days_left} day{'s' if days_left > 1 else ''}* — very soon!"
        emoji   = "⏰"
    else:
        urgency = f"in *{days_left} days* (by {due_date})"
        emoji   = "💊"

    body = (
        f"*PharmAI — Refill Reminder* {emoji}\n\n"
        f"Hi {patient_name}!\n\n"
        f"Your *{medicine_name}* refill is due {urgency}\n\n"
        f"Don't run out — open PharmAI to reorder in seconds.\n\n"
        f"— PharmAI Pharmacy 🏥"
    )
    return _send(patient_phone, body)


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN ALERTS
# ══════════════════════════════════════════════════════════════════════════════

def send_low_stock_alert(
    medicine_name: str,
    current_stock: int,
    product_id:    int,
    threshold:     int = None,
    order_id:      str = None,
) -> dict:
    threshold = threshold or settings.LOW_STOCK_THRESHOLD
    short_oid = str(order_id)[:8].upper() if order_id else "N/A"
    now       = datetime.now().strftime("%d %b %Y, %H:%M")
    urgency   = "🔴 *CRITICAL*" if current_stock <= 3 else "🟡 *LOW STOCK*"

    body = (
        f"*PharmAI Admin Alert* — {urgency}\n\n"
        f"📦 Medicine: *{medicine_name}*\n"
        f"🆔 Product ID: {product_id}\n"
        f"📊 Stock: *{current_stock} units* remaining\n"
        f"⚠️ Threshold: {threshold} units\n"
        f"🔖 Triggered by order: #{short_oid}\n"
        f"🕐 {now}\n\n"
        f"Please restock urgently."
    )
    return _send_admin(body)


def send_out_of_stock_alert(
    medicine_name: str,
    product_id:    int,
    order_id:      str = None,
) -> dict:
    short_oid = str(order_id)[:8].upper() if order_id else "N/A"
    now       = datetime.now().strftime("%d %b %Y, %H:%M")

    body = (
        f"*PharmAI Admin Alert* — 🔴 *OUT OF STOCK*\n\n"
        f"📦 Medicine: *{medicine_name}*\n"
        f"🆔 Product ID: {product_id}\n"
        f"📊 Stock: *0 units* — new orders will be rejected!\n"
        f"🔖 Last order: #{short_oid}\n"
        f"🕐 {now}\n\n"
        f"⚠️ *RESTOCK IMMEDIATELY*"
    )
    return _send_admin(body)


def send_prescription_alert(
    patient_name:  str,
    medicine_name: str,
    patient_id:    str,
) -> dict:
    now = datetime.now().strftime("%d %b %Y, %H:%M")

    body = (
        f"*PharmAI Admin Alert* — 📋 Prescription Review\n\n"
        f"👤 Patient: *{patient_name}* ({patient_id})\n"
        f"💊 Medicine: *{medicine_name}* _(requires prescription)_\n"
        f"🕐 {now}\n\n"
        f"Please verify the uploaded prescription in the admin portal."
    )
    return _send_admin(body)