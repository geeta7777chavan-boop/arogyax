from pydantic import BaseModel
from typing import Optional


class ConversationTurn(BaseModel):
    role:    str   # "user" | "assistant"
    content: str


class ChatOrderIn(BaseModel):
    patient_id:            str
    message:               str
    channel:               str  = "chat"
    prescription_uploaded: bool = False
    rx_medicines:          list = []   # full medicine objects from PrescriptoAI via frontend
    payment_method:        str  = "cash_on_delivery"
    conversation_history:  list[ConversationTurn] = []


class OrderOut(BaseModel):
    order_id:                Optional[str]   = None
    order_status:            Optional[str]   = None
    final_response:          str
    triage_suggestion:       Optional[str]   = None
    product_id:              Optional[int]   = None
    product_name:            Optional[str]   = None
    quantity:                Optional[int]   = None
    unit_price:              Optional[float] = None
    total_price:             Optional[float] = None
    dosage:                  Optional[str]   = None
    safety_approved:         Optional[bool]  = None
    safety_reason:           Optional[str]   = None
    new_stock_level:         Optional[int]   = None
    refill_alert:            Optional[bool]  = None
    refill_medicine:         Optional[str]   = None
    refill_due_date:         Optional[str]   = None
    webhook_triggered:       Optional[bool]  = None
    notification_sent:       Optional[bool]  = None
    langfuse_trace_id:       Optional[str]   = None
    agent_log:               list[dict]      = []
    payment_method:          Optional[str]   = None
    payment_status:          Optional[str]   = None
    pending_product_options: Optional[list]  = None
    delivery_info_provided:  Optional[bool]  = None
    last_agent_response:     Optional[str]   = None
    prescription_rejected:   Optional[bool]  = None
    prescription_uploaded:   Optional[bool]  = None
    # Added this session — displayed in CartReview order summary card
    package_size:            Optional[str]   = None   # e.g. "50 ml", "30 tablets"
    prescription_required:   Optional[bool]  = None   # shown as badge in CartReview


class PrescriptionCheckIn(BaseModel):
    product_id: int


class PrescriptionCheckOut(BaseModel):
    product_id:            int
    product_name:          str
    prescription_required: bool
    message:               str


class OrderConfirmIn(BaseModel):
    patient_id:            str
    product_id:            Optional[int] = None
    product_name:          Optional[str] = None
    quantity:             Optional[int] = None
    dosage:                Optional[str]  = None
    prescription_required: bool           = False
    prescription_uploaded: bool           = False
    payment_method:        str            = "cash_on_delivery"
    channel:               str            = "chat"
    patient_email:         Optional[str]  = None
    patient_name:          Optional[str]  = None
