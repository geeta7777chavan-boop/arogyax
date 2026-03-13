"use client";
// components/admin/InventoryTable.tsx

import { useState, useEffect } from "react";
import { getInventory, updateStock } from "@/lib/api";
import type { Product } from "@/types";
import { clsx } from "clsx";
import { RefreshCw, Search, AlertTriangle, CheckCircle, Edit2, Check, X } from "lucide-react";

export default function InventoryTable() {
  const [products,   setProducts]   = useState<Product[]>([]);
  const [loading,    setLoading]    = useState(true);
  const [search,     setSearch]     = useState("");
  const [lowOnly,    setLowOnly]    = useState(false);
  const [editId,     setEditId]     = useState<number | null>(null);
  const [editValue,  setEditValue]  = useState("");
  const [saving,     setSaving]     = useState(false);

  async function load() {
    setLoading(true);
    try {
      const data = await getInventory({ search, low_stock: lowOnly });
      setProducts(data);
    } catch (error: any) {
      // Network errors mean backend is unavailable - show empty state
      if (error.code === 'ERR_NETWORK' || error.message?.includes('Network Error')) {
        console.log("Backend unavailable - showing empty inventory");
        setProducts([]);
        return;
      }
      console.error("Failed to load inventory:", error);
      setProducts([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [search, lowOnly]);

  async function saveStock(productId: number) {
    const qty = parseInt(editValue);
    if (isNaN(qty) || qty < 0) return;
    setSaving(true);
    try {
      await updateStock(productId, qty);
      setProducts(prev => prev.map(p => p.id === productId ? { ...p, stock_quantity: qty } : p));
      setEditId(null);
    } finally {
      setSaving(false);
    }
  }

  function stockColor(qty: number) {
    if (qty === 0)  return "text-red-400";
    if (qty <= 10)  return "text-yellow-400";
    return "text-brand-400";
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted" />
          <input
            type="text"
            placeholder="Search medicines..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full bg-surface-2 border border-white/5 focus:border-brand-400/40 rounded-xl pl-9 pr-4 py-2.5 text-sm text-ink-primary placeholder-ink-muted font-body focus:outline-none transition-colors"
          />
        </div>
        <label className="flex items-center gap-2 text-xs text-ink-secondary font-body cursor-pointer select-none">
          <input
            type="checkbox"
            checked={lowOnly}
            onChange={e => setLowOnly(e.target.checked)}
            className="accent-yellow-400"
          />
          Low stock only
        </label>
        <button
          onClick={load}
          className="p-2.5 bg-surface-2 border border-white/5 rounded-xl text-ink-secondary hover:text-brand-400 hover:border-brand-400/30 transition-all"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-white/5">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-surface-1 border-b border-white/5">
              {["Medicine", "PZN", "Price", "Package", "Stock", "Rx Required", "Edit"].map(h => (
                <th key={h} className="text-left px-4 py-3 text-xs font-mono text-ink-muted uppercase tracking-wider">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {loading && (
              <tr><td colSpan={7} className="text-center py-8 text-ink-muted text-xs font-mono">Loading inventory...</td></tr>
            )}
            {!loading && products.length === 0 && (
              <tr><td colSpan={7} className="text-center py-8 text-ink-muted text-xs font-mono">No products found.</td></tr>
            )}
            {products.map(p => (
              <tr key={p.id} className="bg-surface-0 hover:bg-surface-1 transition-colors">
                <td className="px-4 py-3 font-body text-ink-primary max-w-[220px]">
                  <span className="block truncate" title={p.name}>{p.name}</span>
                </td>
                <td className="px-4 py-3 font-mono text-ink-muted text-xs">{p.pzn}</td>
                <td className="px-4 py-3 font-mono text-ink-secondary">€{p.price.toFixed(2)}</td>
                <td className="px-4 py-3 text-ink-muted text-xs font-body">{p.package_size}</td>
                <td className="px-4 py-3">
                  {editId === p.id ? (
                    <input
                      type="number"
                      value={editValue}
                      onChange={e => setEditValue(e.target.value)}
                      className="w-20 bg-surface-2 border border-brand-400/40 rounded-lg px-2 py-1 text-xs font-mono text-ink-primary focus:outline-none"
                      autoFocus
                      min="0"
                    />
                  ) : (
                    <span className={clsx("font-mono font-medium flex items-center gap-1", stockColor(p.stock_quantity))}>
                      {p.stock_quantity === 0 && <AlertTriangle size={12} />}
                      {p.stock_quantity}
                    </span>
                  )}
                </td>
                <td className="px-4 py-3">
                  {p.prescription_required
                    ? <span className="text-yellow-400 font-mono text-xs flex items-center gap-1"><AlertTriangle size={11} /> Yes</span>
                    : <span className="text-brand-400 font-mono text-xs flex items-center gap-1"><CheckCircle size={11} /> No</span>
                  }
                </td>
                <td className="px-4 py-3">
                  {editId === p.id ? (
                    <div className="flex gap-1">
                      <button onClick={() => saveStock(p.id)} disabled={saving}
                        className="p-1.5 bg-brand-500/20 border border-brand-400/30 rounded-lg text-brand-400 hover:bg-brand-500/30 transition-colors">
                        <Check size={12} />
                      </button>
                      <button onClick={() => setEditId(null)}
                        className="p-1.5 bg-red-500/10 border border-red-400/20 rounded-lg text-red-400 hover:bg-red-500/20 transition-colors">
                        <X size={12} />
                      </button>
                    </div>
                  ) : (
                    <button onClick={() => { setEditId(p.id); setEditValue(String(p.stock_quantity)); }}
                      className="p-1.5 text-ink-muted hover:text-brand-400 hover:bg-surface-2 rounded-lg transition-colors">
                      <Edit2 size={12} />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-ink-muted font-mono">{products.length} products</p>
    </div>
  );
}
