"""
routers/decisions.py
=====================
GET /decisions          — paginated decision ledger (judge view)
GET /decisions/{id}     — single decision entry with full CoT
GET /decisions/order/{order_id} — all decisions for a specific order
"""

from fastapi import APIRouter, HTTPException, Query
from core.database import supabase

router = APIRouter(prefix="/decisions", tags=["Decision Ledger"])


@router.get("")
def get_decisions(
    agent:  str = Query("", description="Filter by agent name e.g. SafetyAgent"),
    action: str = Query("", description="Filter by action e.g. APPROVE"),
    limit:  int = Query(50, ge=1, le=200),
    offset: int = Query(0,  ge=0),
):
    """
    Return the full decision ledger — the Chain of Thought audit trail.
    Judges use this to see exactly how every agent reasoned.
    """
    query = (
        supabase.table("decision_ledger")
        .select("*")
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if agent:
        query = query.eq("agent_name", agent)
    if action:
        query = query.eq("action", action)

    resp = query.execute()
    return {
        "count":     len(resp.data or []),
        "decisions": resp.data or [],
    }


@router.get("/order/{order_id}")
def get_decisions_for_order(order_id: str):
    """Return all agent decisions related to a specific order — full trace."""
    resp = (
        supabase.table("decision_ledger")
        .select("*")
        .eq("order_id", order_id)
        .order("created_at", desc=False)
        .execute()
    )
    return {
        "order_id":  order_id,
        "decisions": resp.data or [],
    }


@router.get("/{decision_id}")
def get_decision(decision_id: str):
    """Return a single decision entry with full input/output payload."""
    resp = (
        supabase.table("decision_ledger")
        .select("*")
        .eq("id", decision_id)
        .single()
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Decision not found.")
    return resp.data