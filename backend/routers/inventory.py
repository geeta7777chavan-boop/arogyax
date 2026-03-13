"""
routers/inventory.py
====================
GET  /inventory              — list all products with live stock
GET  /inventory/{id}         — single product
PATCH /inventory/{id}/stock  — update stock level (admin)
GET  /inventory/low-stock-alerts — get products with stock below threshold
"""

from fastapi import APIRouter, HTTPException, Query
from core.database import supabase
from models.product import ProductOut, StockUpdateIn

router = APIRouter(prefix="/inventory", tags=["Inventory"])

# Default threshold for low stock alerts
DEFAULT_LOW_STOCK_THRESHOLD = 10


@router.get("", response_model=list[ProductOut])
def get_inventory(
    low_stock: bool = Query(False, description="Filter only low-stock items (≤10 units)"),
    search:    str  = Query("",    description="Search by medicine name"),
):
    """Return full inventory. Optionally filter low-stock or search by name."""
    query = supabase.table("products").select("*").order("name")

    if low_stock:
        query = query.lte("stock_quantity", 10)
    if search:
        query = query.ilike("name", f"%{search}%")

    resp = query.execute()
    return resp.data or []


@router.get("/low-stock-alerts")
def get_low_stock_alerts(threshold: int = Query(DEFAULT_LOW_STOCK_THRESHOLD, description="Stock threshold for alerts")):
    """
    Return products with stock below the specified threshold.
    Used by admin dashboard for low stock notifications.
    """
    resp = (
        supabase.table("products")
        .select("id, pzn, name, price, package_size, description, stock_quantity, prescription_required")
        .lt("stock_quantity", threshold)
        .order("stock_quantity", desc=False)
        .execute()
    )
    
    products = resp.data or []
    
    # Format the response
    alerts = [
        {
            "product_id": p["id"],
            "pzn": p["pzn"],
            "name": p["name"],
            "price": p["price"],
            "package_size": p["package_size"],
            "description": p["description"],
            "stock_quantity": p["stock_quantity"],
            "prescription_required": p["prescription_required"],
            "threshold": threshold,
            "severity": "critical" if p["stock_quantity"] <= 5 else "warning"
        }
        for p in products
    ]
    
    return {
        "count": len(alerts),
        "threshold": threshold,
        "alerts": alerts
    }


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int):
    """Return a single product by ID."""
    resp = (
        supabase.table("products")
        .select("*")
        .eq("id", product_id)
        .single()
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Product not found.")
    return resp.data


@router.patch("/{product_id}/stock")
def update_stock(product_id: int, body: StockUpdateIn):
    """Manually update stock level — used by admin dashboard."""
    if body.stock_quantity < 0:
        raise HTTPException(status_code=422, detail="Stock cannot be negative.")

    resp = (
        supabase.table("products")
        .update({"stock_quantity": body.stock_quantity})
        .eq("id", product_id)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Product not found.")

    # Log manual stock update to decision_ledger for traceability
    supabase.table("decision_ledger").insert({
        "agent_name":     "AdminAction",
        "action":         "MANUAL_STOCK_UPDATE",
        "reason":         f"Admin manually set stock for product {product_id} to {body.stock_quantity}.",
        "input_payload":  {"product_id": product_id},
        "output_payload": {"new_stock": body.stock_quantity},
    }).execute()

    return {"product_id": product_id, "new_stock_quantity": body.stock_quantity}
