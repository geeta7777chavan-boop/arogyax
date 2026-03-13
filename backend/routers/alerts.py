"""
routers/router_alerts.py
=========================
GET  /refill-alerts/check/{patient_id}  ← NEW: called on chat session open
GET  /refill-alerts                     — all pending alerts (admin)
GET  /refill-alerts/{patient_id}        — DB alerts for a patient
POST /refill-alerts/scan                — trigger full predictive scan
PATCH /refill-alerts/{id}              — update alert status
"""

from fastapi import APIRouter, HTTPException
from core.database import supabase
from core.config import settings
from agents.predictive_agent import run_refill_scan_for_all_patients
from services.email_service import run_proactive_refill_scan, send_proactive_refill_email

router = APIRouter(prefix="/refill-alerts", tags=["Refill Alerts"])

# ── Frequency → daily dose count ─────────────────────────────────────────────
FREQ_DAILY: dict[str, float] = {
    "once daily":        1,
    "twice daily":       2,
    "two times daily":   2,
    "three times daily": 3,
    "four times daily":  4,
    "as needed":         0,   # skip — unpredictable
}

# Fallback supply days per pack when package_size unknown
SUPPLY_FALLBACK: dict[str, int] = {
    "once daily":        30,
    "twice daily":       20,
    "three times daily": 14,
    "four times daily":  10,
    "as needed":         0,
}

import re
from datetime import datetime, timedelta


def _parse_pack_units(package_size: str) -> int | None:
    """Extract unit count from package_size string.
    '20x0.5 ml' → 20,  '30 Tabletten' → 30,  '100 ml' → None."""
    if not package_size:
        return None
    s = package_size.strip().lower()
    m = re.match(r'^(\d+)\s*x', s)
    if m:
        return int(m.group(1))
    m = re.search(r'(\d+)\s*(stück|tabletten|kapseln|dragées|dragees|kapsel|tablets?|capsules?|beutel|sachets?|lozenges|pastillen)', s)
    if m:
        return int(m.group(1))
    return None


def _supply_days(freq: str, qty: int, package_size: str = "") -> int | None:
    freq_lower  = (freq or "").strip().lower()
    daily       = FREQ_DAILY.get(freq_lower, 0)
    if daily == 0:
        return None
    pack_units = _parse_pack_units(package_size)
    if pack_units:
        return int((pack_units * max(qty, 1)) / daily)
    base = SUPPLY_FALLBACK.get(freq_lower, 30)
    return base * max(qty, 1)


def _urgency(days: int) -> str:
    if days < 0:   return "overdue"
    if days == 0:  return "today"
    if days <= 5:  return "urgent"
    if days <= 14: return "soon"
    return "ok"


def _friendly(name: str, days: int, is_rx: bool) -> str:
    short = name.split(",")[0].strip()
    rx    = " *(Rx required)*" if is_rx else ""
    if days < 0:   status = f"⚠️ Supply ran out {abs(days)} day(s) ago!"
    elif days == 0: status = "⚠️ Runs out **today**!"
    elif days <= 5: status = f"🔴 Runs out in **{days} day(s)** — refill soon!"
    elif days <= 14: status = f"🟡 Runs out in **{days} days** — time to reorder."
    else:           status = f"🟢 Refill due in {days} days."
    return f"💊 **{short}**{rx} — {status}"


# ── NEW: session-open check ───────────────────────────────────────────────────
@router.get("/check/{patient_id}")
def check_on_session_open(patient_id: str):
    """
    Called by the frontend on chat open.
    Reads order_history, computes supply runout, returns:
      has_alerts, greeting, alerts[], urgency
    """
    pid = patient_id.upper()

    # Get patient name
    patient_name = "there"
    try:
        user_resp = (
            supabase.table("users")
            .select("full_name, first_name")
            .eq("patient_id", pid)
            .single()
            .execute()
        )
        if user_resp.data:
            patient_name = (
                user_resp.data.get("full_name")
                or user_resp.data.get("first_name")
                or "there"
            )
    except Exception:
        pass

    first_name = patient_name.split()[0] if patient_name and patient_name != "there" else "there"

    # Fetch order history
    try:
        hist_resp = (
            supabase.table("order_history")
            .select("medicine_name, product_id, quantity, dosage_frequency, purchase_date")
            .eq("patient_id", pid)
            .order("purchase_date", desc=True)
            .execute()
        )
        history = hist_resp.data or []
    except Exception as e:
        return {"has_alerts": False, "greeting": "", "alerts": [], "urgency": "none",
                "error": str(e)}

    if not history:
        return {"has_alerts": False, "greeting": "", "alerts": [], "urgency": "none"}

    # Batch-fetch package sizes and rx flags
    product_ids = list({r["product_id"] for r in history if r.get("product_id")})
    pkg_map: dict[int, str]  = {}
    rx_map:  dict[int, bool] = {}
    if product_ids:
        try:
            prod_resp = (
                supabase.table("products")
                .select("id, package_size, prescription_required")
                .in_("id", product_ids)
                .execute()
            )
            for p in (prod_resp.data or []):
                pkg_map[p["id"]] = p.get("package_size") or ""
                rx_map[p["id"]]  = bool(p.get("prescription_required", False))
        except Exception:
            pass

    # Latest purchase per medicine
    seen: dict[str, dict] = {}
    for row in history:
        med = (row.get("medicine_name") or "").strip()
        if med and med not in seen:
            seen[med] = row

    today   = datetime.utcnow().date()
    alerts  = []

    for med_name, row in seen.items():
        prod_id  = row.get("product_id")
        qty      = max(int(row.get("quantity") or 1), 1)
        freq     = (row.get("dosage_frequency") or "").strip()
        pkg_size = pkg_map.get(prod_id, "") if prod_id else ""
        is_rx    = rx_map.get(prod_id, False) if prod_id else False

        try:
            last_purchase = datetime.strptime(str(row["purchase_date"])[:10], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            continue

        supply = _supply_days(freq, qty, pkg_size)
        if supply is None:
            continue

        runout    = last_purchase + timedelta(days=supply)
        days_left = (runout - today).days
        urgency   = _urgency(days_left)

        # Only surface overdue/urgent/soon in the greeting (not "ok")
        if urgency in ("overdue", "today", "urgent", "soon"):
            alerts.append({
                "medicine_name":    med_name,
                "product_id":       prod_id,
                "last_purchase":    str(last_purchase),
                "predicted_runout": str(runout),
                "days_until":       days_left,
                "urgency":          urgency,
                "is_rx":            is_rx,
                "dosage_frequency": freq,
                "friendly_message": _friendly(med_name, days_left, is_rx),
            })

    # Sort: most urgent first
    alerts.sort(key=lambda x: x["days_until"])

    if not alerts:
        return {"has_alerts": False, "greeting": "", "alerts": [], "urgency": "none"}

    # Build greeting text (top 3 medicines)
    top = alerts[:3]
    lines = "\n".join(f"  {a['friendly_message']}" for a in top)
    more  = f"\n  _(+{len(alerts)-3} more)_" if len(alerts) > 3 else ""

    greeting = (
        f"Hi {first_name} 👋 Before we start — it looks like you may be running low on:\n\n"
        f"{lines}{more}\n\n"
        "Would you like to refill any of these now? Just say the word!"
    )

    overall = (
        "urgent" if any(a["urgency"] in ("overdue","today","urgent") for a in top)
        else "soon"
    )

    return {
        "has_alerts": True,
        "greeting":   greeting,
        "alerts":     top,
        "urgency":    overall,
    }


# ── Admin: all pending alerts ─────────────────────────────────────────────────
@router.get("")
def get_all_alerts(status: str = "pending"):
    try:
        # Try simple select first without joins to avoid Supabase issues
        resp = (
            supabase.table("refill_alerts")
            .select("*")
            .eq("status", status)
            .order("predicted_refill_date", desc=False)
            .execute()
        )
        alerts = resp.data or []
        
        # Try to get user and product info separately if we have alerts
        # But don't fail if we can't
        return {"count": len(alerts), "alerts": alerts}
    except Exception as e:
        # Log the error for debugging
        print(f"Error fetching alerts: {e}")
        # Return empty instead of crashing
        return {"count": 0, "alerts": [], "error": str(e)}


# ── Patient: DB alerts ────────────────────────────────────────────────────────
@router.get("/{patient_id}")
def get_patient_alerts(patient_id: str):
    pid = patient_id.upper()
    user_resp = (
        supabase.table("users")
        .select("id")
        .eq("patient_id", pid)
        .single()
        .execute()
    )
    if not user_resp.data:
        raise HTTPException(status_code=404, detail=f"Patient '{pid}' not found.")
    user_uuid = user_resp.data["id"]
    resp = (
        supabase.table("refill_alerts")
        .select("*, products(name, price, package_size)")
        .eq("user_id", user_uuid)
        .eq("status", "pending")
        .order("predicted_refill_date")
        .execute()
    )
    return {"patient_id": pid, "alerts": resp.data or []}


# ── Admin: trigger full scan ──────────────────────────────────────────────────
@router.post("/scan")
def trigger_refill_scan():
    alerts = run_refill_scan_for_all_patients()
    return {
        "message": f"Scan complete. {len(alerts)} new refill alerts generated.",
        "alerts":  alerts,
    }


# ── Update alert status ───────────────────────────────────────────────────────
@router.patch("/{alert_id}")
def update_alert_status(alert_id: str, status: str):
    valid = {"pending", "sent", "dismissed", "ordered"}
    if status not in valid:
        raise HTTPException(status_code=422, detail=f"Invalid status. Choose from: {valid}")
    resp = (
        supabase.table("refill_alerts")
        .update({"status": status})
        .eq("id", alert_id)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Alert not found.")
    return {"alert_id": alert_id, "new_status": status}


# ── Proactive Refill Email Scan ───────────────────────────────────────────────
@router.post("/scan-emails")
def trigger_proactive_refill_emails(alert_days: int = 7):
    """
    Trigger proactive refill email scan for all patients.
    Scans patients with recent orders and sends proactive refill emails
    for medications due within alert_days.
    
    Query params:
    - alert_days: Number of days ahead to check for refills (default: 7)
    
    Returns summary of emails sent.
    """
    if not settings.ENABLE_EMAIL_NOTIFICATIONS:
        return {
            "success": False,
            "message": "Email notifications are disabled. Set ENABLE_EMAIL_NOTIFICATIONS=true in .env"
        }
    
    if not settings.SENDGRID_API_KEY:
        return {
            "success": False,
            "message": "SendGrid is not configured. Set SENDGRID_API_KEY in .env"
        }
    
    result = run_proactive_refill_scan(alert_days=alert_days)
    
    return {
        "success": True,
        "message": f"Proactive refill scan complete. Sent {result.get('sent', 0)} emails.",
        "details": result
    }


# ── Send proactive refill email for specific patient ───────────────────────────
@router.post("/send-refill-email/{patient_id}")
def send_refill_email_for_patient(patient_id: str):
    """
    Manually trigger a proactive refill email for a specific patient.
    Checks for medications due and sends email if any found.
    """
    if not settings.ENABLE_EMAIL_NOTIFICATIONS:
        return {
            "success": False,
            "message": "Email notifications are disabled."
        }
    
    if not settings.SENDGRID_API_KEY:
        return {
            "success": False,
            "message": "SendGrid is not configured."
        }
    
    from services.email_service import _check_chronic_med_refills, _get_patient_contact, send_proactive_refill_email
    
    # Get patient contact
    email, name, phone = _get_patient_contact(patient_id.upper())
    
    if not email:
        return {
            "success": False,
            "message": f"No email found for patient {patient_id}"
        }
    
    # Check for due medications
    due_meds = _check_chronic_med_refills(patient_id.upper())
    
    if not due_meds:
        return {
            "success": True,
            "message": f"No medications due for refill for patient {patient_id}",
            "email_sent": False
        }
    
    # Send email
    result = send_proactive_refill_email(
        to_email=email,
        patient_name=name,
        due_meds=due_meds
    )
    
    return {
        "success": result.get("success", False),
        "message": f"Proactive refill email {'sent' if result.get('success') else 'failed'} for {patient_id}",
        "email_sent": result.get("success", False),
        "medications": due_meds
    }
