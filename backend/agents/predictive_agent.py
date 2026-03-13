"""
agents/predictive_agent.py
==========================
LangGraph node: Scans patient history and raises proactive refill alerts.
Runs after InventoryAgent regardless of order outcome.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from agents.state import AgentState
from core.database import supabase
from observability.langfuse_client import log_agent_step

# ── Config ────────────────────────────────────────────────────────────────────
ALERT_WINDOW_DAYS = 30  # Alert if supply runs out within this many days

# Maps dosage frequency to estimated supply days
DOSAGE_SUPPLY_MAP = {
    "once daily": 30,
    "twice daily": 15,
    "three times daily": 10,
    "four times daily": 7,
    "as needed": 30,
    "as directed": 30,
    "once a day": 30,
    "twice a day": 15,
    "every 4 hours": 6,
    "every 6 hours": 4,
    "every 8 hours": 3,
    "weekly": 7,
    "once weekly": 7,
}


def _get_supply_days(dosage: str) -> int:
    """Convert dosage frequency string to estimated supply days."""
    if not dosage:
        return 30  # default
    dosage_lower = dosage.lower().strip()
    for key, days in DOSAGE_SUPPLY_MAP.items():
        if key in dosage_lower:
            return days
    return 30  # default


def _get_patient_history(patient_id: str, limit: int = 50) -> list[dict]:
    """Fetch recent order history for a patient."""
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
        print(f"[PredictiveAgent] Error fetching history: {e}")
        return []


def _get_existing_alerts(user_uuid: str, product_id: int) -> list[dict]:
    """Check for existing pending refill alerts."""
    try:
        resp = (
            supabase.table("refill_alerts")
            .select("product_id")
            .eq("user_id", user_uuid)
            .eq("product_id", product_id)
            .eq("status", "pending")
            .execute()
        )
        return resp.data or []
    except Exception:
        return []


def _upsert_alert(
    user_uuid: str,
    patient_id: str,
    product_id: int,
    product_name: str,
    estimated_empty_date: str,
) -> None:
    """Insert a new refill alert, skip if one already exists."""
    try:
        supabase.table("refill_alerts").insert({
            "user_id":               user_uuid,
            "patient_id":            patient_id.upper(),
            "product_id":            product_id,
            "product_name":          product_name,
            "estimated_empty_date":   estimated_empty_date,
            "status":                "pending",
        }).execute()
        print(f"[PredictiveAgent] Created refill alert for {product_name}")
    except Exception as e:
        print(f"[PredictiveAgent] Alert insert failed (可能已存在): {e}")


def predictive_agent(state: AgentState) -> AgentState:
    """
    LangGraph node: Scans patient history and raises proactive refill alerts.
    Runs after InventoryAgent regardless of order outcome.
    """
    patient_id = state.get("patient_id", "")
    if not patient_id:
        return state

    # Only run after a successful order approval
    if state.get("order_status") != "approved":
        log_agent_step(state, "PredictiveAgent", "SKIPPED", {
            "reason": "Order not approved",
        })
        return state

    # Get current order details
    current_product_id = state.get("product_id")
    current_qty = state.get("extracted_quantity", 1)
    current_dosage = state.get("extracted_dosage", "as directed")

    log_agent_step(state, "PredictiveAgent", "START", {
        "patient_id": patient_id,
        "current_product": state.get("product_name"),
        "current_qty": current_qty,
    })

    # Resolve user UUID
    try:
        user_resp = supabase.table("users").select("id").eq("patient_id", patient_id.upper()).single().execute()
        user_uuid = user_resp.data.get("id") if user_resp.data else None
    except Exception:
        user_uuid = None

    if not user_uuid:
        log_agent_step(state, "PredictiveAgent", "SKIPPED", {"reason": "User not found"})
        return state

    # Scan past orders to find other medicines the patient has bought
    history = _get_patient_history(patient_id)

    # Build a dict: medicine_name -> latest order info
    seen = {}
    for row in history:
        med = row.get("medicine_name") or row.get("name")
        if not med:
            continue
        med = med.strip()
        if med not in seen:
            seen[med] = row   # already ordered desc by date → first is latest

    # For each medicine, check if supply is running low
    refill_candidates = []
    for med, row in seen.items():
        dosage = row.get("dosage_frequency") or "as directed"
        qty_bought = row.get("quantity", 1)

        supply_days = _get_supply_days(dosage)
        last_purchase = row.get("purchase_date")
        if not last_purchase:
            continue

        try:
            last_date = datetime.strptime(last_purchase[:10], "%Y-%m-%d")
            days_ago = (datetime.now() - last_date).days
            days_left = supply_days - days_ago
        except Exception:
            continue

        if 0 <= days_left <= ALERT_WINDOW_DAYS:
            prod_id = row.get("product_id")
            if prod_id and user_uuid:
                existing = _get_existing_alerts(user_uuid, prod_id)
                if not existing:
                    # Write to decision_ledger for traceability
                    supabase.table("decision_ledger").insert({
                        "order_id":    state.get("order_id"),
                        "agent_name":  "PredictiveAgent",
                        "action":      "REFILL_ALERT_CREATED",
                        "reason":      f"Supply of {med} estimated to run out in {days_left} days",
                        "input_payload":  {"medicine": med, "days_left": days_left},
                        "output_payload": {"alert": "REFILL_ALERT"},
                        "langfuse_trace_id": state.get("langfuse_trace_id"),
                    }).execute()
                    _upsert_alert(
                        user_uuid=user_uuid,
                        patient_id=patient_id,
                        product_id=prod_id,
                        product_name=med,
                        estimated_empty_date=(datetime.now() + timedelta(days=days_left)).strftime("%Y-%m-%d"),
                    )
                    refill_candidates.append(med)

    if refill_candidates:
        refill_names = ", ".join(refill_candidates[:3])
        state["refill_alert"] = True
        state["refill_medicine"] = refill_candidates[0]
        # Attach refill message to final response
        existing_resp = state.get("final_response") or ""
        state["final_response"] = existing_resp + (
            f"\n\n💊 *Refill reminder:* Based on your history, you may be running low on "
            f"{refill_names}. Would you like to reorder?"
        )
        log_agent_step(state, "PredictiveAgent", "REFILL_ALERTS_CREATED", {
            "medicines": refill_candidates,
        })
    else:
        log_agent_step(state, "PredictiveAgent", "NO_ALERTS", {})

    return state


# ── Batch runner (for cron) ─────────────────────────────────────────────────
def run_refill_scan_for_all_patients():
    """
    Scan all patients with recent orders and create refill alerts.
    Call this from a scheduled job (e.g., daily cron).
    """
    print("[PredictiveAgent] Running batch refill scan...")
    
    users_resp = supabase.table("users").select("id, patient_id").execute()
    all_alerts = []
    
    for user in users_resp.data or []:
        patient_id = user.get("patient_id")
        user_uuid = user.get("id")
        
        if not patient_id or not user_uuid:
            continue
        
        history = _get_patient_history(patient_id)
        
        seen = {}
        for row in history:
            med = row.get("medicine_name") or row.get("name")
            if not med:
                continue
            med = med.strip()
            if med not in seen:
                seen[med] = row
        
        for med, row in seen.items():
            dosage = row.get("dosage_frequency") or "as directed"
            supply_days = _get_supply_days(dosage)
            last_purchase = row.get("purchase_date")
            
            if not last_purchase:
                continue
            
            try:
                last_date = datetime.strptime(last_purchase[:10], "%Y-%m-%d")
                days_ago = (datetime.now() - last_date).days
                days_left = supply_days - days_ago
            except Exception:
                continue
            
            if 0 <= days_left <= ALERT_WINDOW_DAYS:
                prod_id = row.get("product_id")
                if prod_id:
                    existing = _get_existing_alerts(user_uuid, prod_id)
                    if not existing:
                        _upsert_alert(
                            user_uuid=user_uuid,
                            patient_id=patient_id,
                            product_id=prod_id,
                            product_name=med,
                            estimated_empty_date=(datetime.now() + timedelta(days=days_left)).strftime("%Y-%m-%d"),
                        )
                        all_alerts.append({
                            "patient_id": patient_id,
                            "medicine": med,
                            "days_left": days_left,
                        })
    
    print(f"[PredictiveAgent] Batch scan complete. Created {len(all_alerts)} alerts.")
    return all_alerts

