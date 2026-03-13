"""
agents/refill_analyzer.py
==========================
Analyses a patient's order history to:
1. Detect refill patterns (recurring purchases) and emit refill alerts
2. Resolve "order the same as last time" / "same medicine for cold" requests
   by matching the complaint against past purchases

Called from graph.py as a pre-processing step before ConversationalAgent.
"""

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter
from typing import Optional

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from agents.state import AgentState
from core.database import supabase
from observability.langfuse_client import log_agent_step

# ── Phrases that trigger "last order" resolution ──────────────────────────────
REPEAT_PATTERNS = [
    r"same.*(last time|before|previous|usual)",
    r"(last time|before|previously|usual).*order",
    r"order.*again",
    r"reorder",
    r"refill",
    r"what.*last.*order",
    r"i.*ordered.*before",
    r"same medicine.*for",
    r"same.*i.*bought",
    r"what did i.*order",
    r"my usual",
]

# ── How often a medicine must repeat to count as a pattern (days window) ──────
PATTERN_WINDOW_DAYS = 90
MIN_REPEAT_COUNT    = 2


def _fetch_history(patient_id: str) -> list[dict]:
    """Fetch last 100 orders for a patient from Supabase."""
    try:
        resp = (
            supabase.table("order_history")
            .select("*")
            .eq("patient_id", patient_id.upper())
            .order("purchase_date", desc=True)
            .limit(100)
            .execute()
        )
        return resp.data or []
    except Exception:
        return []


def _fetch_patient_name(patient_id: str) -> Optional[str]:
    """Fetch patient name from users table."""
    try:
        resp = (
            supabase.table("users")
            .select("name")
            .eq("patient_id", patient_id.upper())
            .execute()
        )
        if resp.data and resp.data[0].get("name"):
            return resp.data[0]["name"]
    except Exception:
        pass
    return None


def _is_repeat_request(message: str) -> bool:
    """True if user is asking for the same thing they ordered before."""
    msg = message.lower()
    return any(re.search(pat, msg) for pat in REPEAT_PATTERNS)


def _complaint_keywords_in_history(
    complaint: str, history: list[dict]
) -> list[dict]:
    """
    Return orders whose product name matches keywords for the given complaint.
    Used for "same medicine for cold" type requests.
    """
    COMPLAINT_CLUES: dict[str, list[str]] = {
        "cold":        ["sinupret", "umckaloabo", "mucosolvan", "paracetamol"],
        "cough":       ["mucosolvan", "umckaloabo", "sinupret"],
        "headache":    ["paracetamol", "nurofen", "ibuprofen"],
        "migraine":    ["paracetamol", "nurofen"],
        "fever":       ["paracetamol", "nurofen", "ibuprofen"],
        "allergy":     ["cetirizin", "vividrin", "livocab"],
        "stomach":     ["iberogast", "omni-biotic", "kijimea"],
        "skin":        ["eucerin", "aveeno", "bepanthen", "cetaphil", "fenihydrocort"],
        "eye":         ["vividrin", "cromo", "augentropfen", "hyaluron"],
        "sleep":       ["calmvalera"],
        "vitamin":     ["vitasprint", "centrum", "norsan", "b12"],
        "omega":       ["norsan"],
        "pain":        ["paracetamol", "nurofen", "diclo"],
    }

    complaint_lower = complaint.lower()
    keywords = []
    for key, kws in COMPLAINT_CLUES.items():
        if key in complaint_lower or complaint_lower in key:
            keywords.extend(kws)

    if not keywords:
        return []

    return [
        h for h in history
        if any(kw in (h.get("name") or "").lower() for kw in keywords)
    ]


def _detect_refill_patterns(history: list[dict]) -> list[dict]:
    """
    Identify medicines ordered 2+ times within PATTERN_WINDOW_DAYS.
    Returns list of {medicine, count, last_date, avg_interval_days, next_due}.
    """
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
        name = h.get("name", "").strip()
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
        intervals = [
            (dates[i + 1] - dates[i]).days
            for i in range(len(dates) - 1)
        ]
        avg_interval = int(sum(intervals) / len(intervals)) if intervals else 30
        last_date    = max(dates)
        next_due     = last_date + timedelta(days=avg_interval)
        days_until   = (next_due - datetime.now()).days

        patterns.append({
            "medicine":         name,
            "order_count":      len(dates),
            "last_ordered":     last_date.strftime("%Y-%m-%d"),
            "avg_interval_days": avg_interval,
            "next_due":         next_due.strftime("%Y-%m-%d"),
            "days_until_due":   days_until,
            "overdue":          days_until < 0,
            "due_soon":         0 <= days_until <= 7,
        })

    # Sort by most urgent first
    patterns.sort(key=lambda x: x["days_until_due"])
    return patterns


def refill_analyzer(state: AgentState) -> AgentState:
    """
    Pre-processing node that runs before ConversationalAgent.

    1. Fetches patient order history
    2. Detects refill patterns → sets refill_alert, refill_medicine, refill_due_date
    3. If user asked for "same as last time" → resolves the medicine from history
       and pre-fills extracted_medicine + triage_suggestion so the agent can act on it
    """
    patient_id  = state.get("patient_id", "")
    user_message = (state.get("user_message") or "").strip()
    complaint    = (state.get("primary_complaint") or "").lower()

    if not patient_id:
        return state

    # Fetch patient name for personalized messages
    patient_name = _fetch_patient_name(patient_id)
    if patient_name:
        state["patient_name"] = patient_name

    history = _fetch_history(patient_id)
    if not history:
        return state

    # ── 1. Detect repeat request — ONLY set triage_suggestion if user explicitly asks ──
    is_repeat = _is_repeat_request(user_message)

    if is_repeat:
        resolved = None
        if complaint:
            complaint_matches = _complaint_keywords_in_history(complaint, history)
            if complaint_matches:
                resolved = complaint_matches[0]
        if not resolved and history:
            resolved = history[0]

        if resolved:
            medicine_name = (resolved.get("name") or resolved.get("product_name") or "").strip()
            if medicine_name:
                state["triage_suggestion"]  = medicine_name
                state["extracted_medicine"] = medicine_name
                log_agent_step(state, "RefillAnalyzer", "REPEAT_ORDER_RESOLVED", {
                    "resolved_medicine": medicine_name,
                    "from_date":         resolved.get("purchase_date"),
                })
    # Do NOT set triage_suggestion for non-repeat messages — it bleeds into unrelated turns

    # ── 2. Detect refill patterns ─────────────────────────────────────────────
    patterns = _detect_refill_patterns(history)
    urgent   = [p for p in patterns if p["overdue"] or p["due_soon"]]

    if urgent:
        top = urgent[0]
        state["refill_alert"]    = True
        state["refill_medicine"] = top["medicine"]
        state["refill_due_date"] = top["next_due"]
        log_agent_step(state, "RefillAnalyzer", "REFILL_ALERT", {
            "medicine":    top["medicine"],
            "due":         top["next_due"],
            "order_count": top["order_count"],
        })
    else:
        # No urgent alert — make sure flags are clean
        state.setdefault("refill_alert",    False)
        state.setdefault("refill_medicine", None)
        state.setdefault("refill_due_date", None)

    # ── 3. Attach full pattern analysis to state for API response ─────────────
    state["refill_patterns"] = patterns  # type: ignore[typeddict-unknown-key]

    return state
