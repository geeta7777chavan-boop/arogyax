"""
routers/orders.py
"""

import json
import httpx
import time
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from core.database import supabase
from core.config import settings
from models.order import ChatOrderIn, OrderOut, OrderConfirmIn
from agents.graph import run_pharmacy_agent
from services import email_service

router = APIRouter(prefix="/order", tags=["Orders"])


def _make_response(final_state: dict) -> OrderOut:
    return OrderOut(
        order_id=                final_state.get("order_id"),
        order_status=            final_state.get("order_status"),
        final_response=          final_state.get("final_response") or "No response generated.",
        triage_suggestion=       final_state.get("triage_suggestion"),
        product_id=              final_state.get("product_id"),
        product_name=            final_state.get("product_name"),
        quantity=                final_state.get("extracted_quantity"),
        unit_price=              final_state.get("unit_price"),
        total_price=             final_state.get("total_price"),
        dosage=                  final_state.get("extracted_dosage"),
        safety_approved=         final_state.get("safety_approved"),
        safety_reason=           final_state.get("safety_reason"),
        new_stock_level=         final_state.get("new_stock_level"),
        refill_alert=            final_state.get("refill_alert"),
        refill_medicine=         final_state.get("refill_medicine"),
        refill_due_date=         final_state.get("refill_due_date"),
        webhook_triggered=       final_state.get("webhook_triggered"),
        notification_sent=       final_state.get("notification_sent"),
        langfuse_trace_id=       final_state.get("langfuse_trace_id"),
        agent_log=               final_state.get("agent_log") or [],
        payment_method=          final_state.get("payment_method"),
        payment_status=          final_state.get("payment_status"),
        pending_product_options= final_state.get("pending_product_options"),
        delivery_info_provided=  final_state.get("delivery_info_provided"),
        last_agent_response=     final_state.get("last_agent_response"),
        prescription_rejected=   final_state.get("prescription_rejected", False),
        prescription_uploaded=   final_state.get("prescription_uploaded", False),
        package_size=            final_state.get("package_size"),
        prescription_required=   final_state.get("prescription_required"),
    )


@router.post("", response_model=OrderOut)
async def place_order(body: ChatOrderIn):
    final_state = await run_pharmacy_agent(
        patient_id=            body.patient_id,
        user_message=          body.message,
        channel=               body.channel,
        prescription_uploaded= body.prescription_uploaded,
        rx_medicines=          body.rx_medicines or [],
        payment_method=        body.payment_method,
        conversation_history=  [t.dict() for t in body.conversation_history],
    )
    return _make_response(final_state)


@router.post("/confirm", response_model=OrderOut)
async def confirm_order(body: OrderConfirmIn):
    """
    Called when user clicks 'Place Order' in the cart review UI.
    Writes order + order_items + order_history + decision_ledger to Supabase.
    This is the single source of truth for order creation — the agent pipeline
    only approves/validates; it never writes to the orders table itself.
    """
    # ── Validate required fields ─────────────────────────────────────────────
    if not body.product_id:
        raise HTTPException(
            status_code=422,
            detail="Missing required field: product_id. Please try placing your order again."
        )
    if not body.product_name:
        raise HTTPException(
            status_code=422,
            detail="Missing required field: product_name. Please try placing your order again."
        )
    if not body.quantity or body.quantity < 1:
        raise HTTPException(
            status_code=422,
            detail="Missing or invalid required field: quantity. Please try placing your order again."
        )

    # ── Fetch unit price + package_size from DB (never trust client) ──────────
    product_resp = (
        supabase.table("products")
        .select("price,package_size")
        .eq("id", body.product_id)
        .single()
        .execute()
    )
    if not product_resp.data:
        raise HTTPException(status_code=404, detail="Product not found.")

    unit_price   = float(product_resp.data.get("price", 0.0))
    package_size = product_resp.data.get("package_size") or None
    qty          = body.quantity
    total        = round(unit_price * qty, 2)

    # ── Resolve user UUID from patient_id ─────────────────────────────────────
    # Use maybe_single() instead of single() to avoid PGRST116 error when user doesn't exist
    # Also wrap in try-except to handle None response from Supabase
    # Note: If no user is found (guest checkout), we'll use None for user_id
    # but the orders table requires user_id to be NOT NULL, so we need to handle this
    user_uuid = None
    try:
        user_resp = (
            supabase.table("users")
            .select("id")
            .eq("patient_id", body.patient_id.upper())
            .maybe_single()
            .execute()
        )
        if user_resp and user_resp.data:
            user_uuid = user_resp.data.get("id")
    except Exception as e:
        print(f"[confirm_order] ⚠️ User lookup failed: {e}")
    
    # If no user found via patient_id, try to find by email from auth if available
    # For now, if user_uuid is still None, we'll allow guest checkout with NULL user_id
    # This requires the orders table to have nullable user_id OR we create a fallback

    payment_method = body.payment_method or "cash_on_delivery"
    payment_status = "pending_cod" if payment_method == "cash_on_delivery" else "mock_paid"

    # ── Create order ──────────────────────────────────────────────────────────
    order_resp = supabase.table("orders").insert({
        "user_id":               user_uuid,
        "status":                "approved",
        "total_amount":          total,
        "prescription_uploaded": body.prescription_uploaded,
        "channel":               body.channel or "chat",
        "notes": (
            f"Payment: {payment_method.replace('_', ' ').title()} | "
            f"Payment status: {payment_status}"
        ),
    }).execute()

    order_id = order_resp.data[0]["id"]

    # ── Order items ───────────────────────────────────────────────────────────
    supabase.table("order_items").insert({
        "order_id":         order_id,
        "product_id":       body.product_id,
        "quantity":         qty,
        "unit_price":       unit_price,
        "dosage_frequency": body.dosage or "",
    }).execute()

    # ── Decrement stock ───────────────────────────────────────────────────────
    current = (
        supabase.table("products")
        .select("stock_quantity")
        .eq("id", body.product_id)
        .single()
        .execute()
    )
    current_qty = int(current.data.get("stock_quantity", 0)) if current.data else 0
    new_qty     = max(0, current_qty - qty)

    result = supabase.table("products").update(
        {"stock_quantity": new_qty}
    ).eq("id", body.product_id).execute()

    if not result.data:
        print(
            f"[confirm_order] ⚠️ Stock update for product_id={body.product_id} returned no data. "
            f"Check Supabase RLS policies (UPDATE may be blocked)."
        )


    # Store the current timestamp with timezone info for accurate time display.
    # Using a simple ISO format without timezone suffix ensures the frontend
    # displays the time as stored (helpful for debugging) while still showing
    # the exact time the order was placed.
    # Get current timestamp with timezone awareness
    now = datetime.now()
    # Format as ISO string with time component (e.g., "2026-03-07T14:30:00")
    purchase_datetime = now.strftime("%Y-%m-%dT%H:%M:%S")
    
    print(f"[confirm_order] DEBUG - Writing to order_history: patient_id={body.patient_id.upper()}, product_name={body.product_name}, qty={qty}")
    
    # Try to get user_uuid from users table based on patient_id
    # If user doesn't exist, we'll use None for user_id but still write to order_history
    # Wrap in try-except to handle None response from Supabase
    lookup_user_uuid = None
    try:
        user_lookup = supabase.table("users").select("id").eq("patient_id", body.patient_id.upper()).execute()
        lookup_user_uuid = user_lookup.data[0]["id"] if user_lookup and user_lookup.data else None
    except Exception as e:
        print(f"[confirm_order] ⚠️ User lookup failed: {e}")
        lookup_user_uuid = None
    
    # Write to order_history table
    order_history_data = {
        "patient_id":            body.patient_id.upper(),
        "user_id":               lookup_user_uuid,
        "purchase_date":         purchase_datetime,
        "medicine_name":         body.product_name or "",
        "quantity":              qty,
        "total_price":           total,
        "dosage_frequency":      body.dosage or "As directed",
        "prescription_required": "Yes" if body.prescription_required else "No",
    }
    print(f"[confirm_order] DEBUG - order_history insert data: {order_history_data}")
    
    history_resp = supabase.table("order_history").insert(order_history_data).execute()
    print(f"[confirm_order] DEBUG - order_history insert response: {history_resp}")
    
    if not history_resp.data:
        print(f"[confirm_order] ⚠️ order_history insert returned no data")

    # ── Decision ledger ───────────────────────────────────────────────────────
    try:
        supabase.table("decision_ledger").insert({
            "order_id":   order_id,
            "agent_name": "InventoryAgent",
            "action":     "ORDER_CONFIRMED_BY_USER",
            "reason": (
                f"User confirmed order for {qty}x '{body.product_name}'. "
                f"Stock: {current_qty} → {new_qty}."
            ),
            "input_payload": {
                "product_id":     body.product_id,
                "quantity":       qty,
                "payment_method": payment_method,
            },
            "output_payload": {
                "order_id":        order_id,
                "new_stock_level": new_qty,
                "payment_status":  payment_status,
            },
        }).execute()
    except Exception as e:
        print(f"[confirm_order] ⚠️ decision_ledger write failed: {e}")

    # ── Low stock alert ───────────────────────────────────────────────────────
    if new_qty < 10:
        try:
            supabase.table("decision_ledger").insert({
                "order_id":   order_id,
                "agent_name": "InventoryAgent",
                "action":     "LOW_STOCK_ALERT",
                "reason":     f"Stock for '{body.product_name}' dropped to {new_qty} units.",
                "input_payload":  {"product_id": body.product_id, "new_stock": new_qty},
                "output_payload": {"alert": "LOW_STOCK"},
            }).execute()
        except Exception:
            pass

    # ── Send order confirmation email ─────────────────────────────────────────
    # Use email from request body first (provided by frontend), then fall back to DB lookup
    patient_email = body.patient_email
    patient_name = body.patient_name or "Customer"
    patient_phone = ""
    patient_address = ""
    
    print(f"[confirm_order] DEBUG - Looking for email for patient_id: {body.patient_id}")
    print(f"[confirm_order] DEBUG - Email from request body: {patient_email}")
    
    # If no email from request body, try to look up from database
    if not patient_email:
        try:
            # First try to find by patient_id in users table
            user_email_resp = (
                supabase.table("users")
                .select("email,phone,full_name,first_name")
                .eq("patient_id", body.patient_id.upper())
                .maybe_single()
                .execute()
            )
            
            # If not found by patient_id, try to find by user_uuid in profiles
            if not (user_email_resp and user_email_resp.data) and user_uuid:
                user_email_resp = (
                    supabase.table("profiles")
                    .select("email,phone,full_name")
                    .eq("id", user_uuid)
                    .maybe_single()
                    .execute()
                )
            
            # Last resort: try to find in auth.users using user_uuid
            if not (user_email_resp and user_email_resp.data) and user_uuid:
                try:
                    # Query auth.users directly - this is the authoritative source for email
                    auth_resp = supabase.auth.admin.get_user(user_uuid)
                    if auth_resp and auth_resp.user:
                        patient_email = auth_resp.user.email
                        patient_phone = auth_resp.user.phone or ""
                        print(f"[confirm_order] DEBUG - Got email from auth.users: {patient_email}")
                except Exception as auth_err:
                    print(f"[confirm_order] DEBUG - Could not query auth.users: {auth_err}")
            
            if user_email_resp and user_email_resp.data:
                patient_email = patient_email or user_email_resp.data.get("email")
                patient_phone = user_email_resp.data.get("phone") or patient_phone
                # Use full_name or first_name as patient name (only if not provided in request)
                if not body.patient_name:
                    patient_name = (
                        user_email_resp.data.get("full_name") 
                        or user_email_resp.data.get("first_name") 
                        or patient_email.split("@")[0] if patient_email else "Customer"
                    ).title()
                print(f"[confirm_order] DEBUG - Patient: {patient_name}, Email: {patient_email}")
        except Exception as e:
            print(f"[confirm_order] ⚠️ Failed to fetch user data: {e}")
    
    # ── Send order confirmation email ─────────────────────────────────────────
    if patient_email and settings.ENABLE_EMAIL_NOTIFICATIONS:
        print(f"[confirm_order] Sending order confirmation email to {patient_email}")
        try:
            # Format estimated delivery (tomorrow between 10 AM - 2 PM)
            tomorrow = datetime.now() + timedelta(days=1)
            estimated_delivery = tomorrow.strftime("%d %B %Y") + " between 10 AM – 2 PM"
            
            start_email = time.time()
            email_result = email_service.send_order_confirmation_email(
                to_email=patient_email,
                patient_name=patient_name,
                medicine_name=body.product_name,
                quantity=qty,
                total_price=total,
                order_id=order_id,
                payment_method=payment_method,
                delivery_address=patient_address or "Address not provided",
                estimated_delivery=estimated_delivery,
                order_date=datetime.now().strftime("%d %B %Y"),
                unit_price=unit_price,
                package_size=package_size,
                prescription_verified=body.prescription_uploaded,
                sync=True,
            )
            email_duration = time.time() - start_email
            print(f"[confirm_order] Email sent in {email_duration:.2f}s: {email_result}")
            print(f"[confirm_order] Email result: {email_result}")
        except Exception as e:
            print(f"[confirm_order] ⚠️ Email send failed: {e}")
    else:
        if not patient_email:
            print(f"[confirm_order] ⚠️ No patient email found for {body.patient_id}")
        if not settings.ENABLE_EMAIL_NOTIFICATIONS:
            print(f"[confirm_order] ⚠️ Email notifications are disabled")

    # ── Check and send proactive refill alert ─────────────────────────────────
    # After order confirmation, check if any other medications are due for refill
    if patient_email and settings.ENABLE_EMAIL_NOTIFICATIONS:
        print(f"[confirm_order] DEBUG - Checking proactive refill for patient {body.patient_id}")
        try:
            # Import the proactive refill functions
            from services.email_service import _check_chronic_med_refills
            
            # Check for medications due for refill
            due_meds = _check_chronic_med_refills(body.patient_id.upper(), alert_days=7)
            
            if due_meds:
                print(f"[confirm_order] DEBUG - Found {len(due_meds)} medications due for refill")
                # Send proactive refill email
                from services.email_service import send_proactive_refill_email
                
                refill_result = send_proactive_refill_email(
                    to_email=patient_email,
                    patient_name=patient_name,
                    due_meds=due_meds,
                )
                print(f"[confirm_order] Proactive refill email result: {refill_result}")
            else:
                print(f"[confirm_order] DEBUG - No medications due for refill found")
        except Exception as e:
            print(f"[confirm_order] ⚠️ Proactive refill check failed: {e}")

    return OrderOut(
        order_id=                order_id,
        order_status=            "approved",
        final_response=          "Order confirmed! Thank you for your purchase.",
        triage_suggestion=       None,
        product_id=              body.product_id,
        product_name=            body.product_name,
        quantity=                qty,
        unit_price=              unit_price,
        total_price=             total,
        dosage=                  body.dosage,
        safety_approved=         True,
        safety_reason=           None,
        new_stock_level=         new_qty,
        refill_alert=            None,
        refill_medicine=         None,
        refill_due_date=         None,
        webhook_triggered=       False,
        notification_sent=       False,
        langfuse_trace_id=       None,
        agent_log=               [],
        payment_method=          payment_method,
        payment_status=          payment_status,
        pending_product_options= None,
        delivery_info_provided=  None,
        last_agent_response=     None,
        prescription_rejected=   False,
        prescription_uploaded=   body.prescription_uploaded,
        package_size=            package_size,
        prescription_required=   body.prescription_required,
    )


@router.post("/voice", response_model=OrderOut)
async def place_order_voice(
    patient_id:            str        = Form(...),
    prescription_uploaded: bool       = Form(False),
    payment_method:        str        = Form("cash_on_delivery"),
    conversation_history:  str        = Form("[]"),
    audio:                 UploadFile = File(...),
):
    try:
        history = json.loads(conversation_history)
    except Exception:
        history = []

    audio_bytes = await audio.read()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                files={
                    "file": (
                        audio.filename or "audio.webm",
                        audio_bytes,
                        audio.content_type,
                    )
                },
                data={
                    "model":           settings.GROQ_WHISPER_MODEL,
                    "response_format": "json",
                    "language":        "en",
                },
            )
            resp.raise_for_status()
            transcript = resp.json().get("text", "").strip()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Whisper transcription failed: {str(e)}")

    if not transcript:
        raise HTTPException(status_code=400, detail="Could not transcribe audio.")

    final_state = await run_pharmacy_agent(
        patient_id=            patient_id,
        user_message=          transcript,
        channel=               "voice",
        prescription_uploaded= prescription_uploaded,
        payment_method=        payment_method,
        conversation_history=  history,
    )

    resp_out = _make_response(final_state)
    resp_out.final_response = f'[Heard: "{transcript}"]\n\n{resp_out.final_response}'
    return resp_out


@router.get("/{order_id}")
def get_order(order_id: str):
    order = (
        supabase.table("orders")
        .select("*")
        .eq("id", order_id)
        .single()
        .execute()
    )
    if not order.data:
        raise HTTPException(status_code=404, detail="Order not found.")
    items = (
        supabase.table("order_items")
        .select("*, products(name,price,package_size)")
        .eq("order_id", order_id)
        .execute()
    )
    return {"order": order.data, "items": items.data or []}


@router.patch("/{order_id}/status")
def update_order_status(order_id: str, status: str):
    valid = {"pending", "approved", "rejected", "dispatched", "delivered", "cancelled"}
    if status not in valid:
        raise HTTPException(status_code=422, detail=f"Choose from: {valid}")
    resp = supabase.table("orders").update({"status": status}).eq("id", order_id).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Order not found.")
    try:
        supabase.table("decision_ledger").insert({
            "order_id":       order_id,
            "agent_name":     "AdminAction",
            "action":         "STATUS_UPDATED",
            "reason":         f"Admin set status to '{status}'.",
            "input_payload":  {"order_id": order_id},
            "output_payload": {"new_status": status},
        }).execute()
    except Exception:
        pass
    return {"order_id": order_id, "new_status": status}