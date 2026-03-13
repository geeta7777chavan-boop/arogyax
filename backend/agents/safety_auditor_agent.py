"""
agents/safety_auditor_agent.py
================================
Clinical Auditor — validates medicine matches PRIMARY complaint.
Uses triage_context from state (never re-derives from scratch).
Only runs when primary_complaint is set (triage path).
Skips silently for direct orders.

Updated: includes generic names from rx_medicines for better brand-name matching.
Also skips audit when user explicitly named a product (ORDER intent) so inline Q&A
answers stored in state["inline_qa"] are never discarded by a stale complaint check.
"""

import sys
import json
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from agents.state import AgentState
from core.config import settings
from core.database import supabase
from observability.langfuse_client import log_agent_step

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=settings.GROQ_API_KEY,
    temperature=0.0,
)

AUDITOR_SYSTEM = """You are a Senior Clinical Pharmacist doing a 2-second safety check.

Answer ONLY with valid JSON:
{
  "approved": true | false,
  "reason": "<one sentence>",
  "alternative_category": "<better drug class if rejected, e.g. 'oral analgesic', else null>"
}

Rules:
- approved=true if the medicine directly treats the PRIMARY complaint.
- approved=false if the medicine treats a DIFFERENT condition entirely.
- Examples of WRONG matches (approved=false):
    primary=headache, medicine=Iberogast (digestive aid) -> false
    primary=headache, medicine=Vividrin eye drops -> false
    primary=headache, medicine=Melatonin (sleep aid) -> false
- Examples of CORRECT matches (approved=true):
    primary=headache, medicine=Paracetamol 500mg -> true
    primary=headache, medicine=Nurofen 200mg -> true
    primary=cough, medicine=Bronchipret -> true
    primary=supplement/nutrition, medicine=NORSAN Omega-3 Vegan -> true
    primary=vegan omega-3, medicine=NORSAN Omega-3 Vegan -> true
    primary=allergy, medicine=Allegra 120 (Fexofenadine) -> true
    primary=allergy, medicine=Wysolone (Prednisolone, steroid for allergy/inflammation) -> true
    primary=pain/fever, medicine=Pacimol 650 (Paracetamol) -> true
    primary=inflammation, medicine=Wysolone (Prednisolone) -> true
    primary=hay fever, medicine=Cromo-ratiopharm Augentropfen (cromoglicic acid eye drops) -> true
    primary=eye allergy, medicine=Cromo-ratiopharm Augentropfen -> true
- Be decisive. If there is ANY reasonable clinical link -> approve.
Output ONLY the JSON."""


def _extract_json(text: str) -> str:
    text = text.strip()
    bt   = chr(96) * 3
    for marker in [bt + "json", bt]:
        if text.startswith(marker):
            text = text[len(marker):].strip()
        if text.endswith(marker):
            text = text[:-len(marker)].strip()
    return text.strip()


def safety_auditor_agent(state: AgentState) -> AgentState:
    product_name      = state.get("product_name")
    primary_complaint = state.get("primary_complaint") or ""
    triage_context    = state.get("triage_context")    or ""

    # ── Skip for direct orders (no triage path) ──────────────────────────────
    # Also skips when there is no primary_complaint, which is always the case
    # for explicit-order messages like "I need to order X" — this ensures
    # inline_qa stored by conversational_agent is never discarded here.
    if not primary_complaint:
        log_agent_step(state=state, agent="SafetyAuditor", action="SKIPPED",
                       details={"reason": "No primary complaint — direct order, skip audit."})
        return state

    if not product_name:
        return state

    # ── Skip when user explicitly named the product they want ────────────────
    # Covers: "order X", "I need to order X. How long will 20 units last?" etc.
    # We must respect the user's explicit choice and not second-guess it with a
    # clinical mismatch check. Also prevents inline_qa from being discarded.
    if state.get("user_requested_medicine"):
        log_agent_step(state=state, agent="SafetyAuditor", action="SKIPPED",
                       details={"reason": "User explicitly named product — respecting choice.",
                                "product": state.get("user_requested_medicine")})
        return state

    # ── Skip if complaint was cleared mid-conversation (user switched context) ─
    # e.g. asked about cough -> said forget it -> asked for skin product
    conversation_history = state.get("conversation_history") or []
    ABANDON_PHRASES = [
        "forget about", "forget it", "ignore that", "never mind", "don't worry",
        "skip that", "cancel that", "nope i want", "no i want", "no i need",
        "instead order", "just order", "just get me", "for my skin", "for my hair",
        "for my face", "for my eyes", "for my stomach", "for my back",
    ]
    for turn in reversed(conversation_history[-6:]):
        if turn.get("role") == "user":
            content_lower = turn.get("content", "").lower()
            if any(phrase in content_lower for phrase in ABANDON_PHRASES):
                log_agent_step(state=state, agent="SafetyAuditor", action="SKIPPED",
                               details={
                                   "reason": "User switched product context — skipping stale complaint audit.",
                                   "trigger": content_lower[:80],
                               })
                return state

    log_agent_step(state=state, agent="SafetyAuditor", action="AUDIT_START",
                   details={"medicine": product_name, "complaint": primary_complaint})

    # Build generic name hints from rx_medicines so auditor recognises brand names
    rx_medicines  = state.get("rx_medicines") or []
    generic_hints = ""
    if rx_medicines:
        hints = []
        for m in rx_medicines:
            if isinstance(m, dict):
                name    = m.get("name",    "")
                generic = m.get("generic", "") or m.get("genericName", "")
                if name and generic:
                    hints.append(f"{name} (generic: {generic})")
        if hints:
            generic_hints = "\nKnown generics from prescription: " + ", ".join(hints)

    prompt = (
        f"PRIMARY COMPLAINT: {primary_complaint}\n"
        f"PATIENT CONTEXT: {triage_context[:300]}\n"
        f"SELECTED MEDICINE: {product_name}"
        f"{generic_hints}\n\n"
        f"Does this medicine clinically treat the primary complaint?"
    )

    raw = None
    try:
        resp  = llm.invoke([
            SystemMessage(content=AUDITOR_SYSTEM),
            HumanMessage(content=prompt),
        ])
        raw   = _extract_json(resp.content.strip())
        audit = json.loads(raw)
    except Exception as e:
        # Non-fatal — pass through if auditor fails
        log_agent_step(state=state, agent="SafetyAuditor", action="AUDIT_ERROR",
                       details={"error": str(e), "raw": raw or ""})
        return state

    approved     = audit.get("approved", True)
    reason       = audit.get("reason",   "")
    alt_category = audit.get("alternative_category") or ""

    log_agent_step(state=state, agent="SafetyAuditor", action="AUDIT_RESULT",
                   details={"approved": approved, "reason": reason})

    # Log to decision ledger
    try:
        supabase.table("decision_ledger").insert({
            "agent_name":     "SafetyAuditor",
            "action":         "CLINICAL_AUDIT",
            "reason":         reason,
            "input_payload":  {"medicine": product_name, "complaint": primary_complaint},
            "output_payload": {"approved": approved, "alternative": alt_category},
            "langfuse_trace_id": state.get("langfuse_trace_id"),
        }).execute()
    except Exception:
        pass  # ledger write failure is non-fatal

    if not approved:
        correction = f"I want to make sure you get the right medicine. {reason}"
        if alt_category:
            correction += (
                f" For {primary_complaint}, I'll look for a {alt_category} instead. "
                f"Could you confirm you'd like me to find an alternative?"
            )

        # Discard inline_qa — order is being redirected, not confirmed
        state["inline_qa"]              = None
        state["product_id"]             = None
        state["product_name"]           = None
        state["prescription_required"]  = None
        state["extracted_medicine"]     = None
        state["audit_approved"]         = False
        state["audit_reason"]           = reason
        state["clarification_needed"]   = True
        state["clarification_question"] = correction
        state["order_status"]           = "needs_clarification"
        state["final_response"]         = correction

        log_agent_step(state=state, agent="SafetyAuditor", action="REJECTED",
                       details={"correction": correction})
    else:
        state["audit_approved"] = True
        state["audit_reason"]   = reason

    return state