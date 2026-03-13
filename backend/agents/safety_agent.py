"""
agents/safety_agent.py
=======================
Safety & Policy Agent — validates stock, prescription requirements,
and detects contraindication substitutions, generating a clinical
explanation when a dangerous drug was swapped for a safe alternative.

Prescription validation: when prescription_required=True, checks the
Supabase prescriptions table to verify the uploaded prescription
actually contains the requested medicine using 4-layer fuzzy matching.

Also accepts rx_medicines list passed directly from frontend (fast path,
no DB call needed — medicines extracted by PrescriptoAI and sent in request).
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from agents.state import AgentState
from core.database import supabase
from core.config import settings
from observability.langfuse_client import log_agent_step

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

# ── LLM clients ───────────────────────────────────────────────────────────────
llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=settings.GROQ_API_KEY,
    temperature=0.0,
)

llm_response = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=settings.GROQ_API_KEY,
    temperature=0.5,
)

# ── Contraindication map ──────────────────────────────────────────────────────
CONTRAINDICATION_MAP: dict[str, list[str]] = {
    "stomach ulcer":        ["ibuprofen", "aspirin", "diclofenac", "naproxen"],
    "ulcer":                ["ibuprofen", "aspirin", "diclofenac", "naproxen"],
    "gastric ulcer":        ["ibuprofen", "aspirin", "diclofenac", "naproxen"],
    "peptic ulcer":         ["ibuprofen", "aspirin", "diclofenac", "naproxen"],
    "blood thinner":        ["ibuprofen", "aspirin", "diclofenac", "naproxen"],
    "blood thinners":       ["ibuprofen", "aspirin", "diclofenac", "naproxen"],
    "warfarin":             ["ibuprofen", "aspirin", "diclofenac", "naproxen"],
    "anticoagulant":        ["ibuprofen", "aspirin", "diclofenac", "naproxen"],
    "anticoagulants":       ["ibuprofen", "aspirin", "diclofenac", "naproxen"],
    "kidney disease":       ["ibuprofen", "naproxen", "diclofenac"],
    "liver disease":        ["paracetamol", "acetaminophen"],
    "asthma":               ["aspirin", "ibuprofen"],
    "heart failure":        ["ibuprofen", "naproxen", "diclofenac"],
    "heart condition":      ["ibuprofen", "aspirin", "naproxen", "diclofenac"],
    "cardiac":              ["ibuprofen", "aspirin", "naproxen", "diclofenac"],
    "pregnancy":            ["aspirin", "ibuprofen", "diclofenac"],
    "hypertension":         ["ibuprofen", "naproxen"],
    "high blood pressure":  ["ibuprofen", "naproxen"],
    "lisinopril":           ["ibuprofen", "naproxen", "aspirin"],
    "amlodipine":           ["ibuprofen", "naproxen"],
    "allergy to aspirin":   ["aspirin"],
    "allergy to ibuprofen": ["ibuprofen"],
}

CONDITION_LABELS: dict[str, str] = {
    "stomach ulcer":        "stomach ulcer",
    "ulcer":                "gastric ulcer",
    "gastric ulcer":        "gastric ulcer",
    "peptic ulcer":         "peptic ulcer",
    "blood thinner":        "blood thinner medication",
    "blood thinners":       "blood thinner medication",
    "warfarin":             "Warfarin (blood thinner)",
    "anticoagulant":        "anticoagulant medication",
    "anticoagulants":       "anticoagulant medication",
    "kidney disease":       "kidney disease",
    "liver disease":        "liver disease",
    "asthma":               "asthma",
    "heart failure":        "heart condition",
    "heart condition":      "heart condition",
    "cardiac":              "cardiac condition",
    "pregnancy":            "pregnancy",
    "hypertension":         "high blood pressure",
    "high blood pressure":  "high blood pressure",
    "lisinopril":           "blood pressure medication (Lisinopril)",
    "amlodipine":           "blood pressure medication (Amlodipine)",
    "allergy to aspirin":   "aspirin allergy",
    "allergy to ibuprofen": "ibuprofen allergy",
}

# ── Prompts ───────────────────────────────────────────────────────────────────
NATURAL_RESPONSE_SYSTEM = (
    "You are a senior clinical pharmacist writing a final message to a patient "
    "after substituting a dangerous drug with a safe alternative.\n\n"
    "REQUIRED FORMAT (follow exactly):\n"
    "I cannot recommend [REQUESTED DRUG] because [SPECIFIC CLINICAL REASON]. "
    "[APPROVED ALTERNATIVE] is a safe and effective option for your [COMPLAINT].\n\n"
    "Then on a new line, append the order confirmation line unchanged.\n\n"
    "QUALITY RULES:\n"
    "1. Name the SPECIFIC drug requested\n"
    "2. Name the SPECIFIC condition or medication (e.g. Lisinopril, Warfarin)\n"
    "3. State the SPECIFIC clinical risk (raises blood pressure, increases bleeding "
    "risk, causes GI bleeding)\n"
    "4. Name the approved alternative and confirm it is safe\n"
    "5. 2 sentences maximum before the order confirmation\n\n"
    "EXAMPLE:\n"
    "I cannot recommend Ibuprofen because it raises blood pressure and interferes "
    "with your Lisinopril. Paracetamol 500mg is a safe and effective option for "
    "your cold symptoms.\n\n"
    "[order confirmation here]"
)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _extract_json(text: str) -> str:
    text = text.strip()
    bt   = chr(96) * 3
    for marker in [bt + "json", bt]:
        if text.startswith(marker):
            text = text[len(marker):].strip()
        if text.endswith(marker):
            text = text[:-len(marker)].strip()
    return text.strip()


def _fetch_stock(product_id: int) -> dict:
    try:
        resp = (
            supabase.table("products")
            .select("id,name,stock_quantity,prescription_required")
            .eq("id", product_id)
            .single()
            .execute()
        )
        return resp.data or {}
    except Exception:
        return {}


def _meaningful_words(s: str) -> set:
    """Words of length >= 4 for overlap matching."""
    return set(re.findall(r"[a-z]{4,}", s.lower()))


def _med_matches(med_name: str, generic: str, product_lower: str) -> bool:
    """
    4-layer fuzzy match between a prescription medicine and a catalogue product.
      L1 — substring both directions
      L2 — first word match  (Wysolone vs Wysolone 10mg)
      L3 — generic name match (Allegra <-> Fexofenadine, Wysolone <-> Prednisolone)
      L4 — shared meaningful words (len >= 4)
    """
    req_words = _meaningful_words(product_lower)
    req_first = product_lower.split()[0] if product_lower.split() else product_lower
    med_first = med_name.split()[0]      if med_name.split()   else med_name
    return (
        med_name      in product_lower                                         or  # L1
        product_lower in med_name                                              or  # L1
        med_first     == req_first                                             or  # L2
        (generic and (generic in product_lower or product_lower in generic))   or  # L3
        bool(_meaningful_words(med_name) & req_words)                             # L4
    )


def _verify_prescription(
    patient_id:   str,
    product_name: str,
    rx_medicines: list | None = None,
) -> tuple[bool, str]:
    """
    Verify that a valid prescription exists containing the requested medicine.

    Checks two sources in order:
      1. rx_medicines list from the frontend request (PrescriptoAI result, zero-latency)
      2. Supabase prescriptions table (latest valid upload for this patient)
    """
    product_lower = product_name.lower().strip()

    # ── Fast path: use medicines list sent directly from frontend ─────────────
    if rx_medicines:
        for entry in rx_medicines:
            if isinstance(entry, dict):
                med_name = (entry.get("name")        or "").lower().strip()
                generic  = (entry.get("generic")     or
                            entry.get("genericName") or "").lower().strip()
            else:
                med_name = str(entry).lower().strip()
                generic  = ""
            if med_name and _med_matches(med_name, generic, product_lower):
                print(f"[SafetyAgent] ✅ Rx match (frontend): '{med_name}' <-> '{product_lower}'")
                return True, f"Prescription verified — {product_name} found on your prescription."

    # ── DB path: query Supabase for latest valid prescription ─────────────────
    try:
        resp = (
            supabase.table("prescriptions")
            .select("id,is_valid,ocr_success,medicines,doctor_name,prescription_date")
            .eq("patient_id",  patient_id.upper())
            .eq("is_valid",    True)
            .eq("ocr_success", True)
            .order("upload_date", desc=True)
            .limit(1)
            .execute()
        )

        if not resp.data:
            return False, "No valid prescription found. Please upload your prescription first."

        prescription = resp.data[0]
        medicines    = prescription.get("medicines") or []

        for med in medicines:
            if isinstance(med, dict):
                med_name = (med.get("name")        or "").lower().strip()
                generic  = (med.get("generic")     or
                            med.get("genericName") or "").lower().strip()
            else:
                med_name = str(med).lower().strip()
                generic  = ""

            if med_name and _med_matches(med_name, generic, product_lower):
                doctor  = prescription.get("doctor_name")       or "your doctor"
                rx_date = prescription.get("prescription_date") or "recently"
                print(f"[SafetyAgent] ✅ Rx match (DB): '{med_name}' <-> '{product_lower}'")
                return True, f"Prescription verified — prescribed by {doctor} on {rx_date}."

        rx_names = [
            m.get("name", "") if isinstance(m, dict) else str(m)
            for m in medicines if m
        ]
        print(f"[SafetyAgent] No match for '{product_name}' | rx has: {rx_names}")
        return False, (
            f"Your prescription does not include {product_name}. "
            f"Medicines on your prescription: {', '.join(rx_names) or 'none detected'}. "
            f"Please upload a prescription that lists this medicine."
        )

    except Exception as e:
        return False, f"Could not verify prescription: {str(e)}"


def _write_ledger(
    state: AgentState,
    decision: str,
    reason: str,
    extra: Optional[dict] = None,
) -> None:
    try:
        supabase.table("decision_ledger").insert({
            "order_id":    state.get("order_id"),
            "agent_name":  "SafetyAgent",
            "action":      decision,
            "reason":      reason,
            "input_payload": {
                "product_id":              state.get("product_id"),
                "product_name":            state.get("product_name"),
                "user_requested_medicine": state.get("user_requested_medicine"),
                "requested_quantity":      state.get("extracted_quantity"),
                "stock_available":         state.get("stock_available"),
                "prescription_required":   state.get("prescription_required"),
                "primary_complaint":       state.get("primary_complaint"),
                **(extra or {}),
            },
            "output_payload": {"decision": decision, "reason": reason},
            "langfuse_trace_id": state.get("langfuse_trace_id"),
        }).execute()
    except Exception:
        pass  # ledger write is non-fatal


def _find_contraindication(state: AgentState) -> tuple[str, str]:
    """
    Returns (condition_label, drug_keyword) if the originally requested drug
    is contraindicated for any condition mentioned in the conversation,
    AND the approved product is actually different (substitution occurred).
    """
    triage_context = (state.get("triage_context")          or "").lower()
    user_message   = (state.get("user_message")            or "").lower()
    requested      = (state.get("user_requested_medicine") or "").lower()
    approved       = (state.get("product_name")            or "").lower()

    if not requested:
        return "", ""

    all_context = triage_context + " " + user_message

    for condition, bad_drugs in CONTRAINDICATION_MAP.items():
        if condition not in all_context:
            continue
        for drug_kw in bad_drugs:
            if drug_kw in requested and drug_kw not in approved:
                return CONDITION_LABELS.get(condition, condition), drug_kw

    return "", ""


def _generate_natural_response(
    state: AgentState,
    condition: str,
    requested_drug: str,
    approved_name: str,
    qty: int,
    order_confirmation: str,
) -> str:
    """LLM-generated clinical explanation for a contraindication substitution."""
    context = (
        f"Patient originally asked for: "
        f"{state.get('user_requested_medicine') or requested_drug}\n"
        f"Patient condition / medication: {condition}\n"
        f"Why contraindicated: {requested_drug} causes harm with {condition}\n"
        f"Approved instead: {approved_name}\n"
        f"Primary complaint: {state.get('primary_complaint') or 'symptoms'}\n"
        f"Quantity: {qty}\n\n"
        f"Order confirmation line (append unchanged at the end):\n"
        f"{order_confirmation}"
    )
    try:
        resp = llm_response.invoke([
            SystemMessage(content=NATURAL_RESPONSE_SYSTEM),
            HumanMessage(content=context),
        ])
        return resp.content.strip()
    except Exception:
        return (
            f"I cannot recommend "
            f"{state.get('user_requested_medicine') or requested_drug} "
            f"because of your {condition}. "
            f"{approved_name} is a safe and effective alternative for your "
            f"{state.get('primary_complaint') or 'symptoms'}.\n\n"
            f"{order_confirmation}"
        )


def _get_inline_qa_prefix(state: AgentState) -> str:
    """
    Retrieve and clear the inline Q&A prefix stored by conversational_agent.
    These are answers to secondary questions asked alongside an order
    (e.g. supply duration, contact lens safety).
    Returns a formatted prefix string ready to prepend, or "".
    """
    inline_qa = (state.get("inline_qa") or "").strip()
    if not inline_qa:
        return ""
    # Clear after retrieval so it isn't re-used
    state["inline_qa"] = None
    if not inline_qa.endswith("\n\n"):
        inline_qa += "\n\n"
    return inline_qa


# ── Main agent ────────────────────────────────────────────────────────────────
def safety_agent(state: AgentState) -> AgentState:

    # Still in clarification loop — nothing to validate yet
    if state.get("order_status") == "needs_clarification":
        return state

    # ── MULTI-MEDICINE ORDER: bypass single-product checks ───────────────────
    # product_id is None for multi-orders; selected_products holds the list.
    if state.get("multi_medicine_order") and state.get("selected_products"):
        inline_prefix = _get_inline_qa_prefix(state)
        state["safety_approved"] = True
        state["safety_reason"]   = "Multi-medicine order approved."
        state["order_status"]    = "approved"
        # Preserve any inline Q&A on the existing final_response
        if inline_prefix and state.get("final_response"):
            state["final_response"] = inline_prefix + state["final_response"]
        log_agent_step(state, "SafetyAgent", "MULTI_ORDER_APPROVED", {
            "products":   [p.get("name") for p in state.get("selected_products", [])],
            "quantities": state.get("multi_quantities", []),
        })
        return state

    # No product resolved yet
    if not state.get("product_id"):
        reason = (
            f"Could not identify "
            f"'{state.get('extracted_medicine') or 'requested medicine'}' "
            f"in our catalogue."
        )
        state["safety_approved"] = False
        state["safety_reason"]   = reason
        state["order_status"]    = "rejected"
        state["final_response"]  = (
            "We couldn't find that medicine in our catalogue. "
            "Could you check the name or describe your symptoms instead?"
        )
        state["inline_qa"] = None  # discard — order not going through
        _write_ledger(state, "REJECT", reason)
        log_agent_step(state, "SafetyAgent", "REJECT", {"reason": reason})
        return state

    log_agent_step(state, "SafetyAgent", "START", {
        "product_name":            state.get("product_name"),
        "user_requested_medicine": state.get("user_requested_medicine"),
        "primary_complaint":       state.get("primary_complaint"),
    })

    # ── Live stock fetch ──────────────────────────────────────────────────────
    product       = _fetch_stock(state["product_id"])
    stock         = product.get("stock_quantity", 0)
    rx_req        = product.get("prescription_required", False)
    requested_qty = state.get("extracted_quantity") or 1
    rx_uploaded   = state.get("prescription_uploaded", False)
    rx_medicines  = state.get("rx_medicines") or []

    state["stock_available"]       = stock
    state["prescription_required"] = rx_req

    # ── Prescription verification ─────────────────────────────────────────────
    prescription_verified = True   # non-Rx medicines always pass
    prescription_detail   = ""

    if rx_req:
        if not rx_uploaded:
            prescription_verified = False
            prescription_detail   = (
                "This medicine needs a valid prescription before we can prepare your order. "
                "No worries — simply tap the 📎 Upload Prescription button below, "
                "upload a clear photo of your prescription, and we'll get this sorted right away."
            )
        else:
            patient_id   = state.get("patient_id", "")
            product_name = state.get("product_name", "")
            prescription_verified, prescription_detail = _verify_prescription(
                patient_id   = patient_id,
                product_name = product_name,
                rx_medicines = rx_medicines,
            )
            if not prescription_verified:
                prescription_detail = (
                    f"Almost there! We just need a prescription that includes "
                    f"{product_name} before we can process your order. "
                    f"Please tap the 📎 Upload Prescription button below and upload "
                    f"the correct prescription — we'll take care of the rest."
                )

        log_agent_step(state, "SafetyAgent", "PRESCRIPTION_CHECK", {
            "rx_required":  rx_req,
            "rx_uploaded":  rx_uploaded,
            "rx_verified":  prescription_verified,
            "rx_medicines": [m.get("name") if isinstance(m, dict) else m
                             for m in rx_medicines],
            "detail":       prescription_detail,
        })

    # ── Stock = 0: reject immediately ─────────────────────────────────────────
    if stock == 0:
        decision = "REJECT"
        reason   = "Out of stock."
        state["safety_approved"] = False
        state["safety_reason"]   = reason
        state["order_status"]    = "rejected"
        state["final_response"]  = f"❌ Order cannot be processed. {reason}"
        state["inline_qa"]       = None  # discard
        _write_ledger(state, decision, reason, {"prescription_verified": prescription_verified})
        log_agent_step(state, "SafetyAgent", decision,
                       {"reason": reason, "stock": stock,
                        "prescription_verified": prescription_verified})
        return state

    # ── Insufficient stock: reject ────────────────────────────────────────────
    if stock < requested_qty:
        decision = "REJECT"
        reason   = f"Not enough stock available, only {stock} units are in stock."
        state["safety_approved"] = False
        state["safety_reason"]   = reason
        state["order_status"]    = "rejected"
        state["final_response"]  = f"❌ Order cannot be processed. {reason}"
        state["inline_qa"]       = None  # discard
        _write_ledger(state, decision, reason, {"prescription_verified": prescription_verified})
        log_agent_step(state, "SafetyAgent", decision,
                       {"reason": reason, "stock": stock,
                        "prescription_verified": prescription_verified})
        return state

    # ── Prescription required but not verified: reject ────────────────────────
    if rx_req and not prescription_verified:
        decision = "REJECT"
        reason   = prescription_detail
        state["safety_approved"]      = False
        state["safety_reason"]        = reason
        state["order_status"]         = "rejected"
        state["prescription_rejected"] = True
        state["final_response"]       = f"📋 {prescription_detail}"
        state["inline_qa"]            = None  # discard
        _write_ledger(state, decision, reason, {"prescription_verified": prescription_verified})
        log_agent_step(state, "SafetyAgent", decision,
                       {"reason": reason, "stock": stock,
                        "prescription_verified": prescription_verified})
        return state

    # ── All checks passed — approve ───────────────────────────────────────────
    decision = "APPROVE"
    reason   = "All safety checks passed."
    state["safety_approved"]       = True
    state["safety_reason"]         = reason
    state["order_status"]          = "approved"
    state["prescription_rejected"] = False

    order_confirmation = (
        f"✅ Order approved! {requested_qty}x {state.get('product_name')} "
        f"will be prepared for you."
    )

    # Check for contraindication substitution
    condition, drug_kw = _find_contraindication(state)
    if condition and drug_kw:
        state["contraindication_detected"] = condition
        final = _generate_natural_response(
            state=state,
            condition=condition,
            requested_drug=drug_kw,
            approved_name=state.get("product_name") or "",
            qty=requested_qty,
            order_confirmation=order_confirmation,
        )
        log_agent_step(state, "SafetyAgent", "CONTRAINDICATION_SUBSTITUTION", {
            "condition":        condition,
            "user_requested":   state.get("user_requested_medicine"),
            "approved_instead": state.get("product_name"),
        })
    else:
        final = order_confirmation

    # ── Prepend inline Q&A answers (supply duration, contact lens, etc.) ──────
    # These were stored by conversational_agent when the user asked secondary
    # questions alongside their order. We prepend here because safety_agent is
    # the last agent to write final_response on the approval path.
    inline_prefix = _get_inline_qa_prefix(state)
    state["final_response"] = inline_prefix + final

    _write_ledger(state, decision, reason, {"prescription_verified": prescription_verified})
    log_agent_step(state, "SafetyAgent", decision,
                   {"reason": reason, "stock": stock,
                    "prescription_verified": prescription_verified,
                    "inline_qa_prepended": bool(inline_prefix)})

    return state