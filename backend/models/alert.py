from pydantic import BaseModel
from typing import Optional
from datetime import date


class RefillAlertOut(BaseModel):
    id:                    str
    user_id:               str
    product_id:            int
    last_purchase:         Optional[str]
    predicted_refill_date: Optional[str]
    alert_sent:            bool
    status:                str


class DecisionOut(BaseModel):
    id:               str
    order_id:         Optional[str]
    agent_name:       str
    action:           str
    reason:           str
    input_payload:    Optional[dict]
    output_payload:   Optional[dict]
    langfuse_trace_id: Optional[str]
    created_at:       str
