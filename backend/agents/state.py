from typing import TypedDict, Optional, Literal


class AgentState(TypedDict):
    # ── Input ──────────────────────────────────────────────────────────────────
    session_id:               str
    patient_id:               str
    patient_name:             Optional[str]   # Patient's name for personalized messages
    user_message:             str
    channel:                  str
    payment_method:           Optional[str]
    prescription_uploaded:    Optional[bool]
    prescription_medicines:   list[str]       # medicines extracted from verified prescription
    rx_medicines:             Optional[list]  # full medicine objects from PrescriptoAI via frontend
    conversation_history:     list[dict]      # [{role, content}] from frontend

    # ── Triage context — persisted across ALL nodes, never cleared ─────────────
    primary_complaint:        Optional[str]   # "headache" | "fever" | etc.
    triage_context:           Optional[str]   # full clinical summary for auditor
    stomach_sensitive:        Optional[bool]  # patient has stomach issues → prefer paracetamol
    triage_suggestion:        Optional[str]   # medicine name suggested by triage, awaiting user confirm
    triage_complete:          Optional[bool]  # True if triage can be skipped (direct order detected)

    # ── Conversational Agent ───────────────────────────────────────────────────
    user_requested_medicine:  Optional[str]   # raw drug name user asked for, before any substitution
    extracted_medicine:       Optional[list[str]]  # list of individual medicine names
    extracted_quantity:       Optional[int]
    extracted_dosage:         Optional[str]
    extraction_confidence:    Optional[float]
    clarification_needed:     Optional[bool]
    clarification_question:   Optional[str]
    pending_product_options:  Optional[list]  # product dicts shown as numbered list, awaiting selection

    # ── Multi-medicine order ───────────────────────────────────────────────────
    multi_medicine_order:     Optional[bool]       # True if order contains multiple medicines
    selected_products:        Optional[list[dict]] # product dicts for multi-order
    multi_quantities:         Optional[list[int]]  # quantities per product in multi-order

    # ── Delivery & Repetition Tracking ─────────────────────────────────────────
    delivery_info_provided:   Optional[bool]  # True if last agent message contained delivery info
    last_agent_response:      Optional[str]   # last response text for duplicate detection

    # ── Safety Auditor ─────────────────────────────────────────────────────────
    audit_approved:           Optional[bool]
    audit_reason:             Optional[str]

    # ── Safety Agent ───────────────────────────────────────────────────────────
    product_id:               Optional[int]
    product_name:             Optional[str]
    stock_available:          Optional[int]
    prescription_required:    Optional[bool]
    safety_approved:          Optional[bool]
    safety_reason:            Optional[str]
    contraindication_detected: Optional[str]
    prescription_rejected:    Optional[bool]  # True when rejection is due to missing/invalid Rx

    # ── Inventory Agent ────────────────────────────────────────────────────────
    order_id:                 Optional[str]
    stock_reserved:           Optional[bool]
    new_stock_level:          Optional[int]
    unit_price:               Optional[float]
    total_price:              Optional[float]
    package_size:             Optional[str]   # e.g. "50 ml", "30 tablets" — shown in CartReview
    payment_status:           Optional[str]

    # ── Predictive / Notification ──────────────────────────────────────────────
    refill_alert:             Optional[bool]
    refill_medicine:          Optional[str]
    refill_due_date:          Optional[str]
    refill_patterns:          Optional[list]  # full pattern analysis from RefillAnalyzer
    notification_sent:        Optional[bool]
    notification_channel:     Optional[str]
    webhook_triggered:        Optional[bool]

    # ── Output ─────────────────────────────────────────────────────────────────
    final_response:           Optional[str]
    order_status:             Optional[Literal["approved", "rejected", "pending", "needs_clarification"]]

    # ── Observability ──────────────────────────────────────────────────────────
    langfuse_trace_id:        Optional[str]
    agent_log:                list[dict]