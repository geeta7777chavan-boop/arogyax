import sys
import uuid
import json
import traceback
from pathlib import Path
from langgraph.graph import StateGraph, END

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from agents.state import AgentState
from agents.conversational_agent   import conversational_agent
from agents.safety_auditor_agent   import safety_auditor_agent
from agents.safety_agent           import safety_agent
from agents.inventory_agent        import inventory_agent
from agents.predictive_agent       import predictive_agent
from agents.notification_agent     import notification_agent
from agents.refill_analyzer        import refill_analyzer
from observability.langfuse_client import start_trace, end_trace


def route_after_conversational(state: AgentState) -> str:
    if state.get("order_status") == "needs_clarification":
        return "end"
    # Allow multi-medicine orders through (product_id is None, selected_products has the list)
    if state.get("multi_medicine_order") and state.get("selected_products"):
        return "audit"
    if not state.get("product_id"):
        return "end"
    return "audit"

def route_after_audit(state: AgentState) -> str:
    if state.get("order_status") == "needs_clarification":
        return "end"
    # Allow multi-medicine orders through
    if state.get("multi_medicine_order") and state.get("selected_products"):
        return "safety"
    if not state.get("product_id"):
        return "end"
    return "safety"

def route_after_safety(state: AgentState) -> str:
    return "inventory" if state.get("safety_approved") else "predictive"


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("refill_analyzer",  refill_analyzer)
    g.add_node("conversational",   conversational_agent)
    g.add_node("safety_auditor",   safety_auditor_agent)
    g.add_node("safety",           safety_agent)
    g.add_node("inventory",        inventory_agent)
    g.add_node("predictive",       predictive_agent)
    g.add_node("notification",     notification_agent)

    g.set_entry_point("refill_analyzer")
    g.add_edge("refill_analyzer", "conversational")
    g.add_conditional_edges("conversational", route_after_conversational,
                            {"audit": "safety_auditor", "end": END})
    g.add_conditional_edges("safety_auditor", route_after_audit,
                            {"safety": "safety", "end": END})
    g.add_conditional_edges("safety", route_after_safety,
                            {"inventory": "inventory", "predictive": "predictive"})
    g.add_edge("inventory",   "predictive")
    g.add_edge("predictive",  "notification")
    g.add_edge("notification", END)
    return g.compile()


pharmacy_graph = build_graph()


# ── Delivery keywords (mirrors conversational_agent) ─────────────────────────
_DELIVERY_KEYWORDS = [
    "delivery", "deliver", "arrive", "shipping", "ship", "estimated",
    "arrive within", "arrive by", "delivery time", "will be prepared",
    "ready for pickup", "pickup",
]


def _extract_complaint_from_history(
    history: list[dict],
) -> tuple[str, bool, str, list, bool, str, str, str]:
    """
    Pre-scan conversation history to recover state that must survive across
    stateless API calls.

    Returns:
        complaint               (str)  — primary medical complaint
        stomach_flag            (bool) — patient has stomach sensitivity
        triage_suggestion       (str)  — pending medicine recommendation
        pending_product_options (list) — pending numbered product options
        delivery_info_provided  (bool) — last assistant msg had delivery info
        last_agent_response     (str)  — last assistant message text
        pending_product_id      (str)  — product currently in context (for PRODUCT_QUERY)
        pending_product_name    (str)  — product name currently in context
    """
    import re

    complaint_keywords = {
        "headache": "headache", "migraine": "migraine", "fever": "fever",
        "cough": "cough", "cold": "cold", "flu": "flu",
        "throat": "sore throat", "stomach": "stomach pain",
        "nausea": "nausea", "diarrhea": "diarrhea",
        "allergy": "allergy", "rash": "skin rash",
        "pain": "pain", "ache": "pain", "tired": "fatigue",
    }
    stomach_words = ["stomach", "ulcer", "gastric", "acid", "heartburn",
                     "sensitive stomach", "gut", "ibs"]

    complaint               = ""
    stomach_flag            = False
    triage_suggestion       = ""
    pending_product_options = []
    delivery_info_provided  = False
    last_agent_response     = ""
    pending_product_id      = ""
    pending_product_name    = ""

    all_user_text = " ".join(
        t.get("content", "").lower()
        for t in history if t.get("role") == "user"
    )

    # Get last assistant message
    for turn in reversed(history):
        if turn.get("role") == "assistant":
            last_agent_response = turn.get("content", "")
            break

    # Check if last assistant message contained delivery info
    if last_agent_response:
        last_lower = last_agent_response.lower()
        delivery_info_provided = any(kw in last_lower for kw in _DELIVERY_KEYWORDS)

    # Scan for markers injected by frontend (newest first)
    for turn in reversed(history):
        content = turn.get("content", "")

        # [PENDING_PRODUCT_OPTIONS: [...]] — numbered product list
        if "[PENDING_PRODUCT_OPTIONS:" in content and not pending_product_options:
            m = re.search(r'\[PENDING_PRODUCT_OPTIONS:\s*(\[.+?\])\]', content, re.DOTALL)
            if m:
                try:
                    pending_product_options = json.loads(m.group(1))
                except Exception:
                    pass

        # [PENDING_SUGGESTION: medicine name]
        if "[PENDING_SUGGESTION:" in content and not triage_suggestion:
            m = re.search(r'\[PENDING_SUGGESTION:\s*(.+?)\]', content)
            if m:
                triage_suggestion = m.group(1).strip()

        # [PENDING_PRODUCT: product_id|product_name]
        # Injected by useChat.ts so PRODUCT_QUERY ("how big is the package?")
        # can resolve which product the user is asking about.
        if "[PENDING_PRODUCT:" in content and not pending_product_id:
            m = re.search(r'\[PENDING_PRODUCT:\s*([^|]*)\|([^\]]*)\]', content)
            if m:
                pending_product_id   = m.group(1).strip()
                pending_product_name = m.group(2).strip()

    # Fallback triage_suggestion: scan assistant messages for recommendation phrases
    if not triage_suggestion:
        for turn in reversed(history):
            if turn.get("role") != "assistant":
                continue
            content = turn.get("content", "")
            for phrase in ["I recommend ", "I'd recommend ", "I'd suggest ",
                           "I suggest ", "go with ", "try "]:
                if phrase in content:
                    after     = content.split(phrase, 1)[1]
                    candidate = re.split(r'[,.\n—]', after)[0].strip()
                    skip      = {"you", "that", "this", "it", "a", "an",
                                 "the", "one", "something"}
                    if 3 < len(candidate) < 80 and candidate.lower() not in skip:
                        triage_suggestion = candidate
                        break
            if triage_suggestion:
                break

    # Primary complaint — but ONLY if user hasn't explicitly abandoned it.
    # Check if any recent user message contains an abandon/switch phrase.
    ABANDON_PHRASES = [
        "forget about", "forget it", "ignore that", "never mind",
        "nope i want", "no i want", "no i need", "just order", "just get me",
        "for my skin", "for my hair", "for my face", "skip that", "cancel that",
    ]
    recent_user_msgs = [
        t.get("content", "").lower()
        for t in history[-6:]   # only last 6 turns
        if t.get("role") == "user"
    ]
    user_switched_context = any(
        phrase in msg
        for msg in recent_user_msgs
        for phrase in ABANDON_PHRASES
    )

    if not user_switched_context:
        for kw, label in complaint_keywords.items():
            if kw in all_user_text:
                complaint = label
                break

    stomach_flag = any(w in all_user_text for w in stomach_words)

    return (
        complaint,
        stomach_flag,
        triage_suggestion,
        pending_product_options,
        delivery_info_provided,
        last_agent_response,
        pending_product_id,
        pending_product_name,
    )


async def run_pharmacy_agent(
    patient_id:            str,
    user_message:          str,
    channel:               str        = "chat",
    prescription_uploaded: bool       = False,
    rx_medicines:          list       = None,
    payment_method:        str        = "cash_on_delivery",
    conversation_history:  list[dict] = None,
) -> AgentState:

    session_id = str(uuid.uuid4())
    history    = conversation_history or []

    # Recover persisted state from conversation history markers
    (
        recovered_complaint,
        recovered_stomach,
        recovered_suggestion,
        recovered_options,
        delivery_provided,
        last_response,
        recovered_product_id,
        recovered_product_name,
    ) = _extract_complaint_from_history(history)

    try:
        trace_id = start_trace(session_id=session_id, patient_id=patient_id,
                               user_message=user_message)
    except Exception as e:
        print(f"[WARN] Langfuse: {e}")
        trace_id = session_id

    initial: AgentState = {
        "session_id":             session_id,
        "patient_id":             patient_id,
        "user_message":           user_message,
        "channel":                channel,
        "prescription_uploaded":  prescription_uploaded,
        "rx_medicines":           rx_medicines or [],
        "payment_method":         payment_method,
        "conversation_history":   history,
        "langfuse_trace_id":      trace_id,
        "agent_log":              [],

        # Recovered from history markers — survive stateless API calls
        "primary_complaint":        recovered_complaint or None,
        "triage_context":           "",
        "stomach_sensitive":        recovered_stomach,
        "triage_suggestion":        recovered_suggestion or None,
        "pending_product_options":  recovered_options or None,
        "delivery_info_provided":   delivery_provided,
        "last_agent_response":      last_response,

        # Recovered product context — enables PRODUCT_QUERY follow-ups
        # ("how big is the package?") to know which product is in context
        "product_id":               int(recovered_product_id) if recovered_product_id else None,
        "product_name":             recovered_product_name or None,

        "user_requested_medicine":  None,
        "extracted_medicine":       None,
        "extracted_quantity":       None,
        "extracted_dosage":         None,
        "extraction_confidence":    None,
        "clarification_needed":     None,
        "clarification_question":   None,

        "multi_medicine_order":     None,
        "selected_products":        None,
        "multi_quantities":         None,

        "audit_approved":           None,
        "audit_reason":             None,

        "stock_available":          None,
        "prescription_required":    None,
        "safety_approved":          None,
        "safety_reason":            None,
        "contraindication_detected": None,
        "prescription_rejected":    None,

        "order_id":                 None,
        "stock_reserved":           None,
        "new_stock_level":          None,
        "unit_price":               None,
        "total_price":              None,
        "package_size":             None,
        "payment_status":           None,

        "refill_alert":             None,
        "refill_medicine":          None,
        "refill_due_date":          None,
        "refill_patterns":          None,
        "notification_sent":        None,
        "notification_channel":     None,
        "webhook_triggered":        None,

        "final_response":           None,
        "order_status":             None,
    }

    try:
        final = await pharmacy_graph.ainvoke(initial)
    except Exception as e:
        print("\n" + "="*60)
        print("AGENT PIPELINE ERROR:")
        traceback.print_exc()
        print("="*60 + "\n")
        final = {**initial}
        final["final_response"] = f"Agent error: {str(e)}"
        final["order_status"]   = "rejected"

    try:
        end_trace(trace_id=trace_id, final_state=final)
    except Exception as e:
        print(f"[WARN] Langfuse end: {e}")

    return final