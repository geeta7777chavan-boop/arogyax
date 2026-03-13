"use client";
// components/admin/LowStockAlertPanel.tsx

import { useState, useEffect } from "react";
import { getLowStockAlerts, updateStock } from "@/lib/api";
import type { LowStockAlert } from "@/types";
import { AlertTriangle, Package, RefreshCw, Plus, Minus } from "lucide-react";
import { clsx } from "clsx";

interface LowStockAlertPanelProps {
  threshold?: number;
  onAlertClick?: (alert: LowStockAlert) => void;
}

export default function LowStockAlertPanel({ threshold = 10, onAlertClick }: LowStockAlertPanelProps) {
  const [alerts, setAlerts] = useState<LowStockAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState<number | null>(null);

  async function load() {
    setLoading(true);
    try {
      const { alerts } = await getLowStockAlerts(threshold);
      setAlerts(alerts);
    } catch (error) {
      console.error("Failed to load low stock alerts:", error);
    } finally {
      setLoading(false);
    }
  }

  async function handleRestock(productId: number, currentStock: number, amount: number) {
    setUpdating(productId);
    try {
      const newStock = currentStock + amount;
      await updateStock(productId, newStock);
      await load();
    } catch (error) {
      console.error("Failed to update stock:", error);
    } finally {
      setUpdating(null);
    }
  }

  useEffect(() => {
    load();
  }, [threshold]);

  const criticalAlerts = alerts.filter(a => a.severity === "critical");
  const warningAlerts = alerts.filter(a => a.severity === "warning");

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <AlertTriangle size={15} className="text-yellow-400" />
          <span className="text-sm font-display font-semibold text-ink-primary">
            Low Stock Alerts
          </span>
          {alerts.length > 0 && (
            <span className={clsx(
              "w-5 h-5 rounded-full text-white text-[10px] font-mono font-bold flex items-center justify-center",
              criticalAlerts.length > 0 ? "bg-red-500" : "bg-yellow-500"
            )}>
              {alerts.length}
            </span>
          )}
        </div>
        <button onClick={load} disabled={loading}
          className="p-1.5 text-ink-muted hover:text-brand-400 bg-surface-2 border border-white/5 rounded-lg transition-colors">
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* Critical Alerts */}
      {criticalAlerts.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-mono text-red-400 font-semibold">Critical ({criticalAlerts.length})</p>
          {criticalAlerts.map(alert => (
            <div key={alert.product_id}
              className="flex items-center justify-between gap-3 p-3 rounded-xl border border-red-400/30 bg-red-400/5">
              <div className="flex-1 min-w-0 cursor-pointer" onClick={() => onAlertClick?.(alert)}>
                <div className="flex items-center gap-2 mb-1">
                  <Package size={12} className="text-red-400" />
                  <p className="text-sm font-body text-ink-primary truncate">
                    {alert.name}
                  </p>
                </div>
                <div className="flex items-center gap-3 text-[11px] font-mono text-ink-muted">
                  <span>Stock: <span className="text-red-400 font-bold">{alert.stock_quantity}</span> / {alert.threshold}</span>
                  <span>PZN: {alert.pzn}</span>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => handleRestock(alert.product_id, alert.stock_quantity, 10)}
                  disabled={updating === alert.product_id}
                  className="p-1.5 text-ink-muted hover:text-brand-400 hover:bg-brand-400/10 rounded-lg transition-colors"
                  title="Add 10 units"
                >
                  <Plus size={14} />
                </button>
                <button
                  onClick={() => handleRestock(alert.product_id, alert.stock_quantity, 5)}
                  disabled={updating === alert.product_id}
                  className="p-1.5 text-ink-muted hover:text-brand-400 hover:bg-brand-400/10 rounded-lg transition-colors"
                  title="Add 5 units"
                >
                  <Minus size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Warning Alerts */}
      {warningAlerts.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-mono text-yellow-400 font-semibold">Warning ({warningAlerts.length})</p>
          {warningAlerts.map(alert => (
            <div key={alert.product_id}
              className="flex items-center justify-between gap-3 p-3 rounded-xl border border-yellow-400/30 bg-yellow-400/5">
              <div className="flex-1 min-w-0 cursor-pointer" onClick={() => onAlertClick?.(alert)}>
                <div className="flex items-center gap-2 mb-1">
                  <Package size={12} className="text-yellow-400" />
                  <p className="text-sm font-body text-ink-primary truncate">
                    {alert.name}
                  </p>
                </div>
                <div className="flex items-center gap-3 text-[11px] font-mono text-ink-muted">
                  <span>Stock: <span className="text-yellow-400 font-bold">{alert.stock_quantity}</span> / {alert.threshold}</span>
                  <span>PZN: {alert.pzn}</span>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => handleRestock(alert.product_id, alert.stock_quantity, 10)}
                  disabled={updating === alert.product_id}
                  className="p-1.5 text-ink-muted hover:text-brand-400 hover:bg-brand-400/10 rounded-lg transition-colors"
                  title="Add 10 units"
                >
                  <Plus size={14} />
                </button>
                <button
                  onClick={() => handleRestock(alert.product_id, alert.stock_quantity, 5)}
                  disabled={updating === alert.product_id}
                  className="p-1.5 text-ink-muted hover:text-brand-400 hover:bg-brand-400/10 rounded-lg transition-colors"
                  title="Add 5 units"
                >
                  <Minus size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty State */}
      {!loading && alerts.length === 0 && (
        <div className="text-center py-8 space-y-1">
          <AlertTriangle size={24} className="text-ink-muted mx-auto" />
          <p className="text-xs text-ink-muted font-mono">All stock levels are healthy</p>
        </div>
      )}

      {loading && (
        <p className="text-xs text-ink-muted font-mono text-center py-6">Loading alerts...</p>
      )}
    </div>
  );
}
