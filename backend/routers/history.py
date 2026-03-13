"""
routers/history.py
==================
GET /history/{patient_id}           — full order history for a patient
GET /history/{patient_id}/analysis  — refill patterns + smart insights
GET /history                        — paginated history across all patients (admin)
"""

from fastapi import APIRouter, HTTPException, Query
from core.database import supabase
from datetime import datetime, timedelta
from collections import Counter
import re

router = APIRouter(prefix="/history", tags=["History"])

PATTERN_WINDOW_DAYS = 90
MIN_REPEAT_COUNT    = 2


def _detect_patterns(history: list[dict]) -> list[dict]:
    cutoff = datetime.now() - timedelta(days=PATTERN_WINDOW_DAYS)
    recent = []
    for h in history:
        try:
            d = datetime.strptime(h["purchase_date"][:10], "%Y-%m-%d")
            if d >= cutoff:
                recent.append(h)
        except Exception:
            continue

    name_dates: dict[str, list[datetime]] = {}
    for h in recent:
        name = (h.get("name") or "").strip()
        if not name:
            continue
        try:
            d = datetime.strptime(h["purchase_date"][:10], "%Y-%m-%d")
        except Exception:
            continue
        name_dates.setdefault(name, []).append(d)

    patterns = []
    for name, dates in name_dates.items():
        if len(dates) < MIN_REPEAT_COUNT:
            continue
        dates.sort()
        intervals = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
        avg_interval = int(sum(intervals)/len(intervals)) if intervals else 30
        last_date    = max(dates)
        next_due     = last_date + timedelta(days=avg_interval)
        days_until   = (next_due - datetime.now()).days
        patterns.append({
            "medicine":          name,
            "order_count":       len(dates),
            "last_ordered":      last_date.strftime("%Y-%m-%d"),
            "avg_interval_days": avg_interval,
            "next_due":          next_due.strftime("%Y-%m-%d"),
            "days_until_due":    days_until,
            "overdue":           days_until < 0,
            "due_soon":          0 <= days_until <= 7,
        })

    patterns.sort(key=lambda x: x["days_until_due"])
    return patterns


# ── Analytics endpoint for admin dashboard ────────────────────────────────────
# MUST be defined BEFORE parameterized routes like /{patient_id}
@router.get("/analytics/summary", response_model=dict)
def get_analytics_summary():
    """
    Single endpoint powering the Admin Analytics Dashboard.
    Returns KPIs + time-series + breakdowns in one shot.
    """
    from datetime import date
    import logging
    import traceback
    logger = logging.getLogger(__name__)
    today = date.today()
    
    logger.info("Starting analytics summary generation")

    try:
        # ── All orders from order_history ─────────────────────────────────────────
        # Select all columns to ensure we get the right data
        hist_resp = (
            supabase.table("order_history")
            .select("*")
            .order("purchase_date", desc=True)
            .limit(500)
            .execute()
        )
        all_orders = hist_resp.data or []
        logger.info(f"Fetched {len(all_orders)} orders")
        
        # Log sample order to debug column names
        if all_orders:
            logger.info(f"Sample order keys: {list(all_orders[0].keys())}")
    except Exception as e:
        logger.error(f"Error fetching order_history: {e}")
        logger.error(traceback.format_exc())
        all_orders = []

    try:
        # ── Pending refill alerts ─────────────────────────────────────────────────
        alerts_resp = (
            supabase.table("refill_alerts")
            .select("id, status, predicted_refill_date")
            .eq("status", "pending")
            .execute()
        )
        pending_alerts = alerts_resp.data or []
        logger.info(f"Fetched {len(pending_alerts)} pending alerts")
    except Exception as e:
        logger.error(f"Error fetching refill_alerts: {e}")
        logger.error(traceback.format_exc())
        pending_alerts = []

    try:
        # ── Low stock count ────────────────────────────────────────────────────────
        stock_resp = (
            supabase.table("products")
            .select("id, stock_quantity")
            .lte("stock_quantity", 10)
            .execute()
        )
        low_stock_items = stock_resp.data or []
        logger.info(f"Fetched {len(low_stock_items)} low stock items")
    except Exception as e:
        logger.error(f"Error fetching products: {e}")
        logger.error(traceback.format_exc())
        low_stock_items = []

    try:
        # ── Safety decisions ───────────────────────────────────────────────────────
        decisions_resp = (
            supabase.table("decision_ledger")
            .select("action, agent_name, created_at")
            .in_("action", ["APPROVE", "APPROVE_ORDER", "REJECT",
                            "OUT_OF_STOCK", "PRESCRIPTION_REQUIRED",
                            "STOCK_VALIDATED", "MULTI_ORDER_APPROVED"])
            .order("created_at", desc=True)
            .limit(200)
            .execute()
        )
        decisions = decisions_resp.data or []
        logger.info(f"Fetched {len(decisions)} decisions")
    except Exception as e:
        logger.error(f"Error fetching decision_ledger: {e}")
        logger.error(traceback.format_exc())
        decisions = []

    # ── KPIs ──────────────────────────────────────────────────────────────────
    total_orders   = len(all_orders)
    total_revenue  = sum(float(o.get("total_price") or o.get("price") or 0) for o in all_orders)
    unique_patients = len({o.get("patient_id") for o in all_orders if o.get("patient_id")})
    
    # Debug: Log sample order keys
    if all_orders:
        logger.info(f"Sample order: {all_orders[0]}")

    approved = sum(1 for d in decisions if d["action"] in
                   ("APPROVE", "APPROVE_ORDER", "STOCK_VALIDATED", "MULTI_ORDER_APPROVED"))
    rejected = sum(1 for d in decisions if d["action"] in
                   ("REJECT", "OUT_OF_STOCK", "PRESCRIPTION_REQUIRED"))
    safety_rate = round((approved / (approved + rejected) * 100) if (approved + rejected) > 0 else 100, 1)

    # ── Orders by day (last 14 days) ──────────────────────────────────────────
    from collections import defaultdict
    day_counts:   dict[str, int]   = defaultdict(int)
    day_revenue:  dict[str, float] = defaultdict(float)

    for o in all_orders:
        d = str(o.get("purchase_date") or "")[:10]
        if d:
            day_counts[d]  += 1
            day_revenue[d] += float(o.get("total_price") or 0)

    # Last 14 days sorted
    from datetime import timedelta
    days_series = []
    for i in range(13, -1, -1):
        day = (today - timedelta(days=i)).isoformat()
        days_series.append({
            "date":    day,
            "label":   (today - timedelta(days=i)).strftime("%b %d"),
            "orders":  day_counts.get(day, 0),
            "revenue": round(day_revenue.get(day, 0), 2),
        })

    # ── Top 5 medicines by order count ───────────────────────────────────────
    med_counts: dict[str, dict] = defaultdict(lambda: {"count": 0, "revenue": 0.0})
    for o in all_orders:
        # The actual column name is "medicine_name"
        name = o.get("medicine_name") or o.get("name") or o.get("product_name") or "Unknown"
        name = name.split(",")[0].strip()[:35]
        med_counts[name]["count"]   += 1
        med_counts[name]["revenue"] += float(o.get("total_price") or o.get("price") or 0)

    top_medicines = sorted(med_counts.items(), key=lambda x: x[1]["count"], reverse=True)[:5]
    top_medicines = [{"name": k, **v} for k, v in top_medicines]

    # ── Orders by dosage frequency ────────────────────────────────────────────
    freq_counts: dict[str, int] = defaultdict(int)
    for o in all_orders:
        freq = (o.get("dosage_frequency") or "Unknown").strip()
        freq_counts[freq] += 1
    freq_breakdown = [{"label": k, "count": v} for k, v in
                      sorted(freq_counts.items(), key=lambda x: -x[1])]

    # ── Rx vs OTC split ───────────────────────────────────────────────────────
    rx_count  = sum(1 for o in all_orders if o.get("prescription_required"))
    otc_count = total_orders - rx_count

    # ── Agent action breakdown ────────────────────────────────────────────────
    action_counts: dict[str, int] = defaultdict(int)
    for d in decisions:
        action_counts[d["action"]] += 1

    return {
        "kpis": {
            "total_orders":     total_orders,
            "total_revenue":    round(total_revenue, 2),
            "unique_patients":  unique_patients,
            "pending_alerts":   len(pending_alerts),
            "low_stock_items":  len(low_stock_items),
            "safety_rate":      safety_rate,
        },
        "orders_over_time": days_series,
        "top_medicines":    top_medicines,
        "freq_breakdown":   freq_breakdown,
        "rx_vs_otc":        {"rx": rx_count, "otc": otc_count},
        "agent_actions":    dict(action_counts),
    }


@router.get("/{patient_id}/analysis")
def get_patient_analysis(patient_id: str):
    """Return refill pattern analysis and smart insights for a patient."""
    resp = (
        supabase.table("order_history")
        .select("*")
        .eq("patient_id", patient_id.upper())
        .order("purchase_date", desc=True)
        .limit(100)
        .execute()
    )
    history = resp.data or []
    if not history:
        return {"patient_id": patient_id.upper(), "patterns": [], "alerts": [], "insights": []}

    patterns = _detect_patterns(history)
    alerts   = [p for p in patterns if p["overdue"] or p["due_soon"]]

    # Build human-readable insights
    insights = []
    for p in patterns[:5]:
        if p["overdue"]:
            days_ago = abs(p["days_until_due"])
            insights.append({
                "type":    "overdue",
                "message": f"Your {p['medicine']} refill is {days_ago} day{'s' if days_ago != 1 else ''} overdue.",
                "medicine": p["medicine"],
            })
        elif p["due_soon"]:
            insights.append({
                "type":    "due_soon",
                "message": f"Your {p['medicine']} refill is due in {p['days_until_due']} day{'s' if p['days_until_due'] != 1 else ''}.",
                "medicine": p["medicine"],
            })
        else:
            insights.append({
                "type":    "pattern",
                "message": f"You order {p['medicine']} every ~{p['avg_interval_days']} days. Next due {p['next_due']}.",
                "medicine": p["medicine"],
            })

    return {
        "patient_id": patient_id.upper(),
        "total_orders": len(history),
        "patterns": patterns,
        "alerts":   alerts,
        "insights": insights,
    }


@router.get("/{patient_id}")
def get_patient_history(
    patient_id: str,
    limit:  int = Query(50, ge=1, le=200),
    offset: int = Query(0,  ge=0),
):
    """Return order history for a specific patient, newest first."""
    resp = (
        supabase.table("order_history")
        .select("*")
        .eq("patient_id", patient_id.upper())
        .order("purchase_date", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return {
        "patient_id": patient_id.upper(),
        "count":      len(resp.data or []),
        "history":    resp.data or [],
    }


@router.get("")
def get_all_history(
    limit:  int = Query(100, ge=1, le=500),
    offset: int = Query(0,   ge=0),
):
    """Paginated order history across all patients — admin view."""
    resp = (
        supabase.table("order_history")
        .select("*")
        .order("purchase_date", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return {
        "count":   len(resp.data or []),
        "history": resp.data or [],
    }

