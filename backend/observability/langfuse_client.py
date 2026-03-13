"""
observability/langfuse_client.py
=================================
Langfuse tracing helpers — called by every agent node.

Every agent step:
  1. Logs to Langfuse (visible at cloud.langfuse.com — share link with judges)
  2. Appends to state["agent_log"] (visible in API responses)

Usage:
    from observability.langfuse_client import start_trace, end_trace, log_agent_step
"""

from langfuse import Langfuse
from core.config import settings
from datetime import datetime

# ── Langfuse client singleton ─────────────────────────────────────────────────
langfuse = Langfuse(
    secret_key=settings.LANGFUSE_SECRET_KEY,
    public_key=settings.LANGFUSE_PUBLIC_KEY,
    host=settings.LANGFUSE_HOST,
)

# In-memory store of active traces { session_id → trace object }
_active_traces: dict = {}

# In-memory store of active spans { session_id: { span_key: span_object } }
_active_spans: dict = {}


def start_trace(session_id: str, patient_id: str, user_message: str) -> str:
    """
    Start a new Langfuse trace for a full agent pipeline run.
    Returns the trace_id to store in AgentState.
    """
    trace = langfuse.trace(
        name="pharmacy-agent-pipeline",
        session_id=session_id,
        user_id=patient_id,
        input={"user_message": user_message},
        metadata={"patient_id": patient_id},
    )
    _active_traces[session_id] = trace
    return trace.id


def end_trace(trace_id: str, final_state: dict):
    """Close the Langfuse trace with the final output."""
    session_id = final_state.get("session_id")
    trace = _active_traces.pop(session_id, None)
    if trace:
        trace.update(
            output={
                "order_status":   final_state.get("order_status"),
                "final_response": final_state.get("final_response"),
                "order_id":       final_state.get("order_id"),
            }
        )
    langfuse.flush()


def log_agent_step(
    state: dict,
    agent: str,
    action: str,
    details: dict,
):
    """
    Log a single agent step as a Langfuse span AND append to state["agent_log"].

    Call this at the START and END of every agent node so judges can see:
    - Which agent ran
    - What decision it made
    - Why (CoT in `details`)
    - Exact timestamp
    """
    session_id = state.get("session_id", "unknown")
    timestamp  = datetime.utcnow().isoformat()

    # 1. Append to in-memory agent log (returned in API response)
    log_entry = {
        "timestamp": timestamp,
        "agent":     agent,
        "action":    action,
        "details":   details,
    }
    if "agent_log" in state and isinstance(state["agent_log"], list):
        state["agent_log"].append(log_entry)

    # 2. Create or end Langfuse span under the active trace
    trace = _active_traces.get(session_id)
    if trace:
        # Check if this is a completion action (ends the span with output)
        completion_actions = [
            "COMPLETE", "APPROVE", "REJECT", "SKIPPED", "ERROR",
            "ORDER_RESOLVED", "STOCK_VALIDATED", "NO_ALERTS",
            "PRESCRIPTION_CHECK", "AUDIT_RESULT", "REFILL_ALERTS_CREATED",
            "START", "CLASSIFIED", "DIRECT_ORDER_DETECTED"
        ]
        
        # Initialize spans dict for session if not exists
        if session_id not in _active_spans:
            _active_spans[session_id] = {}
        
        span_key = f"{agent}::{action}"
        
        # If this is a START action, create and store the span
        if action == "START":
            span = trace.span(
                name=f"{agent}::{action}",
                input=details,
                metadata={
                    "agent":      agent,
                    "action":     action,
                    "session_id": session_id,
                },
            )
            _active_spans[session_id][agent] = span
        # If this is a completion/ending action, end the corresponding span
        elif any(action.endswith(ca) or action == ca for ca in completion_actions):
            # Try to end the span for this agent
            stored_span = _active_spans.get(session_id, {}).get(agent)
            if stored_span:
                stored_span.end(
                    output=details
                )
                # Remove from active spans
                if session_id in _active_spans:
                    _active_spans[session_id].pop(agent, None)
            else:
                # If no stored span, create a new one and end it immediately
                trace.span(
                    name=f"{agent}::{action}",
                    input={},
                    output=details,
                    metadata={
                        "agent":      agent,
                        "action":     action,
                        "session_id": session_id,
                    },
                )

    # 3. Flush periodically (Langfuse batches internally — explicit flush on end_trace)
