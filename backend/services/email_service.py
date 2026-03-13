"""
services/email_service.py
=========================
Email notifications using SendGrid SMTP for ArogyaX.

Required env vars:
  SENDGRID_API_KEY  - your SendGrid API key (used as SMTP password)
  EMAIL_FROM        - sender email (e.g., arogyax213@gmail.com)
  EMAIL_FROM_NAME   - sender name (e.g., ArogyaX)

Uses SMTP (port 587) instead of the SendGrid HTTP library to avoid
DNS resolution failures (getaddrinfo failed) on restricted networks.
"""

import sys
import smtplib
import threading
from pathlib import Path
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from core.config import settings
from core.database import supabase

# Currency symbol
CURRENCY_SYMBOL = "€"

# SendGrid SMTP constants
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = None  # set from EMAIL_FROM at runtime


# ── Patient contact lookup ────────────────────────────────────────────────────

def _get_patient_contact(patient_id: str) -> tuple[str, str, str]:
    """Returns (email, name, phone) for a patient."""
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
            name  = email.split("@")[0] if email else "Customer"
            return email, name, phone
    except Exception as e:
        print(f"[EmailService] Could not fetch patient contact: {e}")
    return "", "Customer", settings.USER_PHONE_FALLBACK


# ── Core send function — SMTP ─────────────────────────────────────────────────

def _send_email(to: str, subject: str, html: str, text: str = None) -> dict:
    """
    Send email via Gmail SMTP using an App Password.
    Never raises. Falls back to mock/log if credentials are missing.
    Returns {"success": bool, "error": str}

    Required .env vars:
      EMAIL_FROM=arogyax213@gmail.com
      GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx   (16-char Google App Password)
      EMAIL_FROM_NAME=ArogyaX
    """
    # ── Resolve credentials ────────────────────────────────────────────────
    smtp_user     = getattr(settings, "EMAIL_FROM", "") or ""
    smtp_password = getattr(settings, "GMAIL_APP_PASSWORD", "") or ""

    # ── No credentials → mock log ──────────────────────────────────────────
    if not smtp_password:
        print(f"\n{'─'*50}")
        print(f"[Email MOCK — GMAIL_APP_PASSWORD not set]")
        print(f"To: {to} | Subject: {subject}")
        print(f"{'─'*50}\n")
        return {"success": True, "mock": True}

    if not to:
        return {"success": False, "error": "No recipient email provided"}

    # ── Build MIME message ─────────────────────────────────────────────────
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{settings.EMAIL_FROM_NAME} <{smtp_user}>"
    msg["To"]      = to

    if text:
        msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    # ── Send via Gmail SMTP ────────────────────────────────────────────────
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_password.replace(" ", ""))  # strip spaces if any
            server.sendmail(smtp_user, to, msg.as_string())

        print(f"[Email] ✅ Sent to {to} | Subject: {subject}")
        return {"success": True}

    except smtplib.SMTPAuthenticationError:
        err = "Gmail auth failed — check EMAIL_FROM and GMAIL_APP_PASSWORD in .env"
        print(f"[Email] ❌ {err}")
        return {"success": False, "error": err}

    except smtplib.SMTPException as e:
        err = f"SMTP error: {e}"
        print(f"[Email] ❌ Failed to send to {to}: {err}")
        return {"success": False, "error": err}

    except Exception as e:
        err = str(e)
        print(f"[Email] ❌ Failed to send to {to}: {err}")
        return {"success": False, "error": err}


# ── Fire-and-forget wrapper — doesn't block the agent pipeline ───────────────

def _send_email_bg(to: str, subject: str, html: str, text: str = None) -> None:
    """
    Send email in a background thread so the API response is instant.
    The email arrives a few seconds later but the user gets their
    order confirmation immediately without waiting.
    """
    thread = threading.Thread(
        target=_send_email,
        args=(to, subject, html, text),
        daemon=True,   # thread dies if main process exits — safe for this use case
    )
    thread.start()


# ══════════════════════════════════════════════════════════════════════════════
# ORDER CONFIRMATION EMAIL
# ══════════════════════════════════════════════════════════════════════════════

def send_order_confirmation_email(
    to_email: str,
    patient_name: str,
    medicine_name: str,
    quantity: int,
    total_price: float,
    order_id: str,
    payment_method: str = "cash_on_delivery",
    delivery_address: str = "",
    estimated_delivery: str = "",
    order_date: str = "",
    unit_price: float = 0.0,
    package_size: str = "",
    prescription_verified: bool = False,
    sync: bool = False,   # accepted but ignored — email always sends in background
    **kwargs,             # absorb any other unexpected keyword args gracefully
) -> dict:
    """Send a beautiful order confirmation email with detailed order information."""

    payment_label = "Cash on Delivery" if payment_method == "cash_on_delivery" else "Online Payment"
    amount_label  = "Amount to Pay" if payment_method == "cash_on_delivery" else "Amount Paid"
    short_id      = str(order_id)[:8].upper()

    if not order_date:
        order_date = datetime.now().strftime("%d %B %Y")

    if not estimated_delivery:
        tomorrow = datetime.now() + timedelta(days=1)
        estimated_delivery = f"{tomorrow.strftime('%d %B %Y')} between 10 AM – 2 PM"

    if not delivery_address:
        delivery_address = "Address not provided"

    size_display = f" ({package_size})" if package_size else ""
    subject      = f"Order Confirmed! Your medicines are on the way – #{short_id}"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin:0; padding:0; background-color:#f5f5f5; font-family:'Segoe UI', Arial, sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f5f5f5; padding:20px;">
            <tr>
                <td align="center">
                    <table width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff; border-radius:12px; overflow:hidden; box-shadow:0 4px 12px rgba(0,0,0,0.1);">
                        <tr>
                            <td style="background:linear-gradient(135deg, #0d9488 0%, #14b8a6 100%); padding:30px; text-align:center;">
                                <h1 style="color:#ffffff; margin:0; font-size:28px; font-weight:600;">🌿 ArogyaX</h1>
                                <p style="color:#ccfbf1; margin:5px 0 0 0; font-size:14px;">Your Trusted Pharmacy Partner</p>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding:30px 30px 10px 30px; text-align:center;">
                                <div style="width:80px; height:80px; background-color:#d1fae5; border-radius:50%; display:inline-flex; align-items:center; justify-content:center;">
                                    <span style="font-size:40px;">✅</span>
                                </div>
                                <h2 style="color:#065f46; margin:15px 0 5px 0; font-size:24px;">Order Confirmed!</h2>
                                <p style="color:#6b7280; margin:0; font-size:14px;">Thank you {patient_name} for shopping with us!</p>
                                <p style="color:#065f46; margin:10px 0 0 0; font-size:16px; font-weight:600;">Your order has been successfully placed and is now being prepared.</p>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding:20px 30px;">
                                <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f9fafb; border-radius:8px; border:1px solid #e5e7eb; overflow:hidden;">
                                    <tr style="background-color:#0d9488; color:#ffffff;">
                                        <th style="padding:12px 15px; text-align:left; font-size:12px; text-transform:uppercase;">Order Details</th>
                                        <th style="padding:12px 15px; text-align:right; font-size:12px; text-transform:uppercase;">Value</th>
                                    </tr>
                                    <tr>
                                        <td style="padding:12px 15px; border-bottom:1px solid #e5e7eb;">
                                            <p style="color:#6b7280; margin:0; font-size:11px; text-transform:uppercase;">Order ID</p>
                                            <p style="color:#111827; margin:5px 0 0 0; font-size:14px; font-weight:600;">#{short_id}</p>
                                        </td>
                                        <td style="padding:12px 15px; border-bottom:1px solid #e5e7eb; text-align:right;">
                                            <p style="color:#6b7280; margin:0; font-size:11px; text-transform:uppercase;">Order Date</p>
                                            <p style="color:#111827; margin:5px 0 0 0; font-size:14px;">{order_date}</p>
                                        </td>
                                    </tr>
                                    <tr>
                                        <td style="padding:12px 15px; border-bottom:1px solid #e5e7eb;">
                                            <p style="color:#6b7280; margin:0; font-size:11px; text-transform:uppercase;">Delivery Address</p>
                                            <p style="color:#111827; margin:5px 0 0 0; font-size:14px;">{delivery_address}</p>
                                        </td>
                                        <td style="padding:12px 15px; border-bottom:1px solid #e5e7eb; text-align:right;">
                                            <p style="color:#6b7280; margin:0; font-size:11px; text-transform:uppercase;">Estimated Delivery</p>
                                            <p style="color:#059669; margin:5px 0 0 0; font-size:14px; font-weight:600;">{estimated_delivery}</p>
                                        </td>
                                    </tr>
                                    <tr>
                                        <td style="padding:12px 15px;">
                                            <p style="color:#6b7280; margin:0; font-size:11px; text-transform:uppercase;">Payment Method</p>
                                            <p style="color:#111827; margin:5px 0 0 0; font-size:14px;">{payment_label}</p>
                                        </td>
                                        <td style="padding:12px 15px; text-align:right;">
                                            <p style="color:#6b7280; margin:0; font-size:11px; text-transform:uppercase;">{amount_label}</p>
                                            <p style="color:#059669; margin:5px 0 0 0; font-size:20px; font-weight:700;">€{total_price:.2f}</p>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding:0 30px;">
                                <h3 style="color:#111827; margin:0 0 10px 0; font-size:16px;">Order Items:</h3>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding:0 30px 20px 30px;">
                                <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#ffffff; border-radius:8px; border:1px solid #e5e7eb; overflow:hidden;">
                                    <tr style="background-color:#f3f4f6;">
                                        <th style="padding:10px 15px; text-align:left; font-size:12px; color:#6b7280; text-transform:uppercase;">Medicine</th>
                                        <th style="padding:10px 15px; text-align:center; font-size:12px; color:#6b7280; text-transform:uppercase;">Quantity</th>
                                        <th style="padding:10px 15px; text-align:right; font-size:12px; color:#6b7280; text-transform:uppercase;">Price</th>
                                    </tr>
                                    <tr>
                                        <td style="padding:12px 15px; border-bottom:1px solid #e5e7eb;">
                                            <p style="color:#111827; margin:0; font-size:14px; font-weight:500;">{medicine_name}{size_display}</p>
                                        </td>
                                        <td style="padding:12px 15px; border-bottom:1px solid #e5e7eb; text-align:center;">
                                            <p style="color:#111827; margin:0; font-size:14px;">{quantity} strip{'s' if quantity > 1 else ''}</p>
                                        </td>
                                        <td style="padding:12px 15px; border-bottom:1px solid #e5e7eb; text-align:right;">
                                            <p style="color:#111827; margin:0; font-size:14px;">€{unit_price * quantity:.2f}</p>
                                        </td>
                                    </tr>
                                    <tr style="background-color:#f9fafb;">
                                        <td colspan="2" style="padding:12px 15px; text-align:right;">
                                            <p style="color:#6b7280; margin:0; font-size:14px;">Total (incl. delivery &amp; taxes):</p>
                                        </td>
                                        <td style="padding:12px 15px; text-align:right;">
                                            <p style="color:#059669; margin:0; font-size:18px; font-weight:700;">€{total_price:.2f}</p>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding:0 30px 20px 30px;">
                                <div style="background-color:#ecfdf5; border-radius:8px; padding:15px; border-left:4px solid #10b981;">
                                    <h4 style="color:#065f46; margin:0 0 8px 0; font-size:14px;">📦 Next Steps</h4>
                                    <p style="color:#047857; margin:0 0 5px 0; font-size:13px;">✓ Our team is packing your order right now.</p>
                                    <p style="color:#047857; margin:0 0 5px 0; font-size:13px;">✓ We'll send you a tracking link once it's dispatched.</p>
                                    {"<p style='color:#047857; margin:0; font-size:13px;'>✓ Our pharmacist has verified your prescription — thank you for uploading!</p>" if prescription_verified else ""}
                                </div>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding:0 30px 20px 30px;">
                                <div style="background-color:#f9fafb; border-radius:8px; padding:15px; text-align:center;">
                                    <h4 style="color:#111827; margin:0 0 10px 0; font-size:14px;">Need Help?</h4>
                                    <p style="color:#6b7280; margin:0; font-size:13px;">Any questions? Reply to this email and we'll help right away.</p>
                                </div>
                            </td>
                        </tr>
                        <tr>
                            <td style="background-color:#f9fafb; padding:20px 30px; text-align:center; border-top:1px solid #e5e7eb;">
                                <p style="color:#6b7280; margin:0 0 5px 0; font-size:14px;">
                                    <strong>Warm regards,</strong><br>Team ArogyaX 🌿
                                </p>
                                <p style="color:#9ca3af; margin:10px 0 0 0; font-size:12px;">
                                    support@arogyax.com | Trusted Care, Always There
                                </p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    text = f"""
Order Confirmed! #{short_id}

Hi {patient_name}! Thank you for shopping with ArogyaX!

ORDER DETAILS:
Order ID: #{short_id}
Order Date: {order_date}
Delivery Address: {delivery_address}
Estimated Delivery: {estimated_delivery}
Payment: {payment_label}
Amount: €{total_price:.2f}

ORDER ITEMS:
{medicine_name}{size_display}
Quantity: {quantity} strip{'s' if quantity > 1 else ''}
Price: €{unit_price * quantity:.2f}
Total: €{total_price:.2f}

Our team is packing your order right now.
{"Our pharmacist has verified your prescription!" if prescription_verified else ""}

Warm regards,
Team ArogyaX 🌿
    """

    # Fire-and-forget — API returns instantly, email arrives seconds later
    _send_email_bg(to_email, subject, html, text)
    return {"success": True, "queued": True}


# ══════════════════════════════════════════════════════════════════════════════
# PROACTIVE REFILL ALERTS
# ══════════════════════════════════════════════════════════════════════════════

DOSAGE_SUPPLY_MAP = {
    "once daily": 30, "twice daily": 15, "three times daily": 10,
    "four times daily": 7, "as needed": 30, "as directed": 30,
    "once a day": 30, "twice a day": 15, "every 4 hours": 6,
    "every 6 hours": 4, "every 8 hours": 3, "weekly": 7, "once weekly": 7,
}


def _get_supply_days(dosage: str) -> int:
    if not dosage:
        return 30
    dosage_lower = dosage.lower().strip()
    for key, days in DOSAGE_SUPPLY_MAP.items():
        if key in dosage_lower:
            return days
    return 30


def _get_patient_history(patient_id: str, limit: int = 50) -> list[dict]:
    try:
        resp = (
            supabase.table("order_history")
            .select("medicine_name, product_id, quantity, dosage_frequency, purchase_date")
            .eq("patient_id", patient_id.upper())
            .order("purchase_date", desc=True)
            .limit(limit)
            .execute()
        )
        return resp.data or []
    except Exception as e:
        print(f"[ProactiveRefill] Error fetching history: {e}")
        return []


def _get_product_stock(medicine_name: str) -> int:
    try:
        resp = (
            supabase.table("products")
            .select("stock_quantity")
            .ilike("name", f"%{medicine_name}%")
            .limit(1)
            .execute()
        )
        if resp.data:
            return int(resp.data[0].get("stock_quantity", 0))
    except Exception as e:
        print(f"[ProactiveRefill] Could not fetch stock for {medicine_name}: {e}")
    return 0


def _check_chronic_med_refills(patient_id: str, alert_days: int = 7) -> list[dict]:
    history = _get_patient_history(patient_id)
    if not history:
        return []

    seen = {}
    for row in history:
        med = (row.get("medicine_name") or row.get("name") or "").strip()
        if med and med not in seen:
            seen[med] = row

    due_meds = []
    for med, row in seen.items():
        dosage    = row.get("dosage_frequency") or "as directed"
        qty_bought = row.get("quantity", 1)
        supply_days = _get_supply_days(dosage)
        last_purchase = row.get("purchase_date")
        if not last_purchase:
            continue
        try:
            last_date = datetime.strptime(last_purchase[:10], "%Y-%m-%d")
            days_ago  = (datetime.now() - last_date).days
            days_left = supply_days - days_ago
        except Exception:
            continue

        if days_left <= alert_days:
            due_meds.append({
                "medicine":       med,
                "days_until":     days_left,
                "due_date":       (datetime.now() + timedelta(days=days_left)).strftime("%d %B %Y"),
                "dosage":         dosage,
                "last_purchase":  last_purchase[:10],
                "quantity_bought": qty_bought,
                "current_stock":  _get_product_stock(med),
            })

    return due_meds


def send_proactive_refill_email(
    to_email: str,
    patient_name: str,
    due_meds: list[dict],
    pharmacy_phone: str = "+91XXXXXXXXXX",
) -> dict:
    if not due_meds:
        return {"success": False, "error": "No medications due for refill"}

    meds_html = ""
    meds_text = ""

    for med in due_meds[:5]:
        days          = med.get("days_until", 0)
        med_name      = med.get("medicine", "")
        due_date      = med.get("due_date", "")
        last_purchase = med.get("last_purchase", "Unknown")
        qty_bought    = med.get("quantity_bought", 1)
        dosage        = med.get("dosage", "As directed")
        current_stock = med.get("current_stock", 0)

        if days <= 0:
            emoji, urgency, bg, border, uc = "🚨", "OVERDUE", "#fef2f2", "#fecaca", "#dc2626"
        elif days <= 2:
            emoji, urgency, bg, border, uc = "⏰", f"Due in {days} day{'s' if days>1 else ''}", "#fffbeb", "#fde68a", "#f59e0b"
        else:
            emoji, urgency, bg, border, uc = "💊", f"Due in {days} days", "#ecfdf5", "#a7f3d0", "#059669"

        stock_display = f"{current_stock} strips available" if current_stock > 0 else "Check availability"

        meds_html += f"""
        <tr>
            <td style="padding:15px; border-bottom:1px solid {border};">
                <p style="margin:0; color:#111827; font-weight:600; font-size:15px;">{emoji} {med_name}</p>
                <p style="margin:8px 0 0 0; color:#6b7280; font-size:12px;">Dosage: {dosage}</p>
            </td>
            <td style="padding:15px; border-bottom:1px solid {border}; text-align:right;">
                <p style="margin:0; color:{uc}; font-weight:700; font-size:14px;">{urgency}</p>
                <p style="margin:5px 0 0 0; color:#6b7280; font-size:12px;">Due: {due_date}</p>
            </td>
        </tr>
        <tr>
            <td colspan="2" style="padding:10px 15px 15px 15px; border-bottom:1px solid {border}; background-color:{bg};">
                <table width="100%" cellpadding="0" cellspacing="0"><tr>
                    <td style="padding:0 10px 0 0;">
                        <p style="margin:0; color:#6b7280; font-size:11px;">Last Purchase</p>
                        <p style="margin:3px 0 0 0; color:#111827; font-size:13px; font-weight:500;">{last_purchase}</p>
                    </td>
                    <td style="padding:0 10px 0 0;">
                        <p style="margin:0; color:#6b7280; font-size:11px;">Qty Bought</p>
                        <p style="margin:3px 0 0 0; color:#111827; font-size:13px; font-weight:500;">{qty_bought} tablets</p>
                    </td>
                    <td>
                        <p style="margin:0; color:#6b7280; font-size:11px;">Current Stock</p>
                        <p style="margin:3px 0 0 0; color:#059669; font-size:13px; font-weight:500;">{stock_display}</p>
                    </td>
                </tr></table>
            </td>
        </tr>
        """
        meds_text += f"• {med_name}\n  Last purchase: {last_purchase} | Qty: {qty_bought} | {urgency} (Due: {due_date}) | Stock: {stock_display}\n\n"

    subject = f"💊 Refill Reminder — {len(due_meds)} medication{'s' if len(due_meds) > 1 else ''} due | ArogyaX"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
    <body style="margin:0; padding:0; background-color:#f5f5f5; font-family:'Segoe UI', Arial, sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f5f5f5; padding:20px;">
            <tr><td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff; border-radius:12px; overflow:hidden; box-shadow:0 4px 12px rgba(0,0,0,0.1);">
                    <tr>
                        <td style="background:linear-gradient(135deg,#0d9488 0%,#14b8a6 100%); padding:30px; text-align:center;">
                            <h1 style="color:#ffffff; margin:0; font-size:28px; font-weight:600;">🌿 ArogyaX</h1>
                            <p style="color:#ccfbf1; margin:5px 0 0 0; font-size:14px;">Your Trusted Pharmacy Partner</p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:30px 30px 10px 30px; text-align:center;">
                            <span style="font-size:50px;">💊</span>
                            <h2 style="color:#065f46; margin:15px 0 5px 0; font-size:24px;">Refill Reminder</h2>
                            <p style="color:#6b7280; margin:0; font-size:14px;">Hi {patient_name}, your medications may be running low soon!</p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:20px 30px;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="border-radius:8px; border:1px solid #e5e7eb; overflow:hidden;">
                                <tr style="background-color:#f3f4f6;">
                                    <th style="padding:12px 15px; text-align:left; font-size:12px; color:#6b7280; text-transform:uppercase;">Medication</th>
                                    <th style="padding:12px 15px; text-align:right; font-size:12px; color:#6b7280; text-transform:uppercase;">Status</th>
                                </tr>
                                {meds_html}
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:0 30px 20px 30px; text-align:center;">
                            <p style="color:#6b7280; margin:0 0 10px 0; font-size:14px;">Reply <strong>YES</strong> or <strong>REFILL</strong> to this email to reorder, or call/WhatsApp us at {pharmacy_phone}.</p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:0 30px 20px 30px;">
                            <div style="background-color:#fefce8; border-radius:8px; padding:15px; border-left:4px solid #facc15;">
                                <p style="color:#854d0e; margin:0; font-size:12px;"><strong>⚠️ Safety Disclaimer:</strong> Always consult your doctor before continuing or changing any medication.</p>
                            </div>
                        </td>
                    </tr>
                    <tr>
                        <td style="background-color:#f9fafb; padding:20px 30px; text-align:center; border-top:1px solid #e5e7eb;">
                            <p style="color:#9ca3af; margin:0; font-size:12px;">— ArogyaX 🌿 | support@arogyax.com | Trusted Care, Always There</p>
                        </td>
                    </tr>
                </table>
            </td></tr>
        </table>
    </body>
    </html>
    """

    text = f"""
Refill Reminder — ArogyaX

Hi {patient_name}! Your medications may be running low:

{meds_text}
Reply YES or REFILL to reorder, or call {pharmacy_phone}.

⚠️ Always consult your doctor before continuing any medication.

— ArogyaX 🌿 | support@arogyax.com
    """

    # Fire-and-forget — doesn't block the agent pipeline
    _send_email_bg(to_email, subject, html, text)
    return {"success": True, "queued": True}


def _send_proactive_refill_alert(patient_id: str, due_meds: list[dict] = None) -> bool:
    email, name, phone = _get_patient_contact(patient_id)
    if not email:
        print(f"[ProactiveRefill] No email found for patient {patient_id}")
        return False

    if due_meds is None:
        due_meds = _check_chronic_med_refills(patient_id)

    if not due_meds:
        print(f"[ProactiveRefill] No medications due for {patient_id}")
        return False

    result = send_proactive_refill_email(to_email=email, patient_name=name, due_meds=due_meds)

    try:
        supabase.table("decision_ledger").insert({
            "agent_name":     "ProactiveRefill",
            "action":         "PROACTIVE_REFILL_EMAIL_SENT",
            "reason":         f"Sent refill email for {len(due_meds)} med(s) to {email}",
            "input_payload":  {"patient_id": patient_id, "medications": [m.get("medicine") for m in due_meds]},
            "output_payload": result,
        }).execute()
    except Exception as e:
        print(f"[ProactiveRefill] Failed to log to decision_ledger: {e}")

    return result.get("success", False)


def run_proactive_refill_scan(alert_days: int = 7) -> dict:
    """Scan all patients and send proactive refill emails. Called by daily scheduler."""
    print(f"[ProactiveRefill] Running batch scan with {alert_days} day window...")

    users_resp_data = []
    try:
        orders_resp = supabase.table("orders").select("patient_id, first_name, last_name, email").execute()
        users_resp_data = orders_resp.data or []
        try:
            users_resp = supabase.table("users").select("id, patient_id, email, full_name, first_name").execute()
            if users_resp.data:
                existing_ids = {u.get("patient_id") for u in users_resp_data if u.get("patient_id")}
                for u in users_resp.data:
                    if u.get("patient_id") and u.get("patient_id") not in existing_ids:
                        users_resp_data.append(u)
        except Exception:
            pass
    except Exception as e:
        print(f"[ProactiveRefill] Failed to fetch orders: {e}")
        try:
            users_resp = supabase.table("users").select("id, patient_id, email").execute()
            users_resp_data = users_resp.data or []
        except Exception as e2:
            return {"sent": 0, "failed": 0, "total_checked": 0, "errors": [str(e2)]}

    sent_count = failed_count = 0
    errors = []

    for user in users_resp_data:
        patient_id = user.get("patient_id")
        if not patient_id:
            continue
        try:
            success = _send_proactive_refill_alert(patient_id)
            if success:
                sent_count += 1
            else:
                failed_count += 1
        except Exception as e:
            failed_count += 1
            errors.append(f"{patient_id}: {str(e)}")

    summary = {"sent": sent_count, "failed": failed_count, "total_checked": len(users_resp_data)}
    if errors:
        summary["errors"] = errors

    print(f"[ProactiveRefill] Batch scan complete. Sent: {sent_count}, Failed: {failed_count}")
    return summary


# ══════════════════════════════════════════════════════════════════════════════
# LEGACY REFILL REMINDER (kept for compatibility)
# ══════════════════════════════════════════════════════════════════════════════

def send_refill_reminder_email(
    to_email: str,
    patient_name: str,
    medicine_name: str,
    days_left: int,
    due_date: str,
) -> dict:
    if days_left <= 0:
        urgency, emoji, color = "Your refill is overdue!", "🚨", "#dc2626"
    elif days_left <= 2:
        urgency, emoji, color = f"Due in {days_left} day{'s' if days_left > 1 else ''}", "⏰", "#f59e0b"
    else:
        urgency, emoji, color = f"Due in {days_left} days", "💊", "#0d9488"

    subject = f"{emoji} Refill Reminder — {medicine_name} | ArogyaX"

    html = f"""
    <!DOCTYPE html>
    <html><head><meta charset="utf-8"></head>
    <body style="margin:0; padding:0; background-color:#f5f5f5; font-family:'Segoe UI', Arial, sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f5f5f5; padding:20px;">
            <tr><td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff; border-radius:12px; overflow:hidden;">
                    <tr>
                        <td style="background:linear-gradient(135deg,#0d9488 0%,#14b8a6 100%); padding:30px; text-align:center;">
                            <h1 style="color:#ffffff; margin:0; font-size:28px;">🌿 ArogyaX</h1>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:30px; text-align:center;">
                            <span style="font-size:50px;">{emoji}</span>
                            <h2 style="color:#92400e; margin:15px 0 5px 0;">Refill Reminder</h2>
                            <p style="color:#6b7280;">Hi {patient_name}, it's time to refill your medicine!</p>
                            <div style="background-color:#fefbeb; border-radius:8px; padding:20px; border:1px solid #fcd34d; margin-top:20px;">
                                <p style="color:#92400e; margin:0; font-size:16px; font-weight:600;">{medicine_name}</p>
                                <p style="color:{color}; margin:10px 0 0 0; font-size:18px; font-weight:700;">{urgency}</p>
                                <p style="color:#6b7280; margin:5px 0 0 0; font-size:12px;">Due: {due_date}</p>
                            </div>
                        </td>
                    </tr>
                    <tr>
                        <td style="background-color:#f9fafb; padding:20px 30px; text-align:center; border-top:1px solid #e5e7eb;">
                            <p style="color:#9ca3af; margin:0; font-size:12px;">— ArogyaX 🌿 | support@arogyax.com</p>
                        </td>
                    </tr>
                </table>
            </td></tr>
        </table>
    </body></html>
    """

    text = f"Refill Reminder\n\nHi {patient_name}!\n\n{emoji} {medicine_name}: {urgency}\nDue: {due_date}\n\n— ArogyaX 🌿"

    _send_email_bg(to_email, subject, html, text)
    return {"success": True, "queued": True}