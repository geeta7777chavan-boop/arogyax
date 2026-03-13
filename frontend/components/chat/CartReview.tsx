"use client";
// components/chat/CartReview.tsx
// Shown when agent approves an order — user reviews and clicks "Place Order"

import { useState } from "react";
import { ShoppingCart, CheckCircle, Loader2, Package } from "lucide-react";
import { clsx } from "clsx";
import type { OrderResponse } from "@/types";

interface Props {
  response:      OrderResponse;
  onPlaceOrder:  () => void;
  paymentMethod: "cash_on_delivery" | "online_mock";
}

export default function CartReview({ response, onPlaceOrder, paymentMethod }: Props) {
  const [placing, setPlacing] = useState(false);

  const unitPrice   = response.unit_price                    ?? null;
  const totalPrice  = response.total_price                   ?? null;
  const qty         = response.quantity                      ?? 1;
  const medicine    = response.product_name                  ?? "Medicine";
  const dosage      = (response as any).dosage               ?? null;
  const packageSize = (response as any).package_size         ?? null;
  const rxRequired  = (response as any).prescription_required ?? false;

  function handlePlace() {
    setPlacing(true);
    setTimeout(() => {
      onPlaceOrder();
      setPlacing(false);
    }, 500);
  }

  return (
    <div className="w-full max-w-sm rounded-2xl border border-white/8 bg-surface-1 overflow-hidden shadow-lg">

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 px-4 py-3 bg-surface-2 border-b border-white/5">
        <ShoppingCart size={15} className="text-brand-400" />
        <span className="text-sm font-display font-semibold text-ink-primary">Order Summary</span>
      </div>

      {/* ── Body ───────────────────────────────────────────────────────── */}
      <div className="px-4 py-4 space-y-3">

        {/* Item card */}
        <div className="bg-surface-0 rounded-xl p-3 border border-white/5 space-y-2">

          {/* Top row: name + price */}
          <div className="flex items-start justify-between gap-3">
            <p className="text-sm font-semibold text-ink-primary font-display leading-snug">
              {medicine}
            </p>
            <div className="text-right shrink-0 space-y-0.5">
              {totalPrice !== null && (
                <p className="text-sm font-bold text-ink-primary font-mono">
                  €{totalPrice.toFixed(2)}
                </p>
              )}
              <div className="flex items-center justify-end gap-1 text-brand-400 text-[10px] font-mono">
                <CheckCircle size={10} />
                <span>Ready</span>
              </div>
            </div>
          </div>

          {/* Details grid */}
          <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] font-mono">

            <span className="text-ink-muted">Quantity</span>
            <span className="text-ink-secondary font-semibold">{qty}</span>

            {unitPrice !== null && (
              <>
                <span className="text-ink-muted">Unit price</span>
                <span className="text-ink-secondary">€{unitPrice.toFixed(2)}</span>
              </>
            )}

            {packageSize && (
              <>
                <span className="text-ink-muted flex items-center gap-1">
                  <Package size={9} />Package size
                </span>
                <span className="text-ink-secondary">{packageSize}</span>
              </>
            )}

            {dosage && (
              <>
                <span className="text-ink-muted">Dosage</span>
                <span className="text-ink-secondary">{dosage}</span>
              </>
            )}

            <span className="text-ink-muted">Payment</span>
            <span className="text-ink-secondary">
              {paymentMethod === "cash_on_delivery" ? "Cash on Delivery" : "Online (Mock)"}
            </span>

            {rxRequired && (
              <>
                <span className="text-ink-muted">Prescription</span>
                <span className="text-yellow-400 text-[10px]">Required ✓</span>
              </>
            )}

          </div>
        </div>

        {/* Total row */}
        {totalPrice !== null && (
          <div className="flex items-center justify-between px-1 pt-1 border-t border-white/5">
            <span className="text-sm text-ink-secondary font-body">Total</span>
            <span className="text-base font-bold text-ink-primary font-mono">
              €{totalPrice.toFixed(2)}
            </span>
          </div>
        )}

        {/* Place Order button */}
        <button
          onClick={handlePlace}
          disabled={placing}
          className={clsx(
            "w-full flex items-center justify-center gap-2 py-3 rounded-xl mt-1",
            "text-sm font-display font-semibold transition-all duration-200",
            placing
              ? "bg-brand-600/50 text-white/60 cursor-not-allowed"
              : "bg-brand-600 hover:bg-brand-500 text-white active:scale-[0.98] shadow-md shadow-brand-600/20"
          )}
        >
          {placing ? (
            <><Loader2 size={15} className="animate-spin" /> Placing order...</>
          ) : (
            <><CheckCircle size={15} /> Place Order</>
          )}
        </button>

      </div>
    </div>
  );
}