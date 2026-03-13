"use client";
// components/admin/AlertsPanel.tsx

import { useState, useEffect } from "react";
import { getRefillAlerts, dismissAlert, triggerRefillScan } from "@/lib/api";
import type { RefillAlert } from "@/types";
import { Bell, RefreshCw, X, Zap } from "lucide-react";
import { format, parseISO, differenceInDays } from "date-fns";
import { clsx } from "clsx";

export default function AlertsPanel() {
  const [alerts,   setAlerts]   = useState<RefillAlert[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [scanning, setScanning] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const { alerts } = await getRefillAlerts("pending");
      setAlerts(alerts);
    } finally {
      setLoading(false);
    }
  }

  async function scan() {
    setScanning(true);
    try {
      await triggerRefillScan();
      await load();
    } finally {
      setScanning(false);
    }
  }

  async function dismiss(id: string) {
    await dismissAlert(id);
    setAlerts(prev => prev.filter(a => a.id !== id));
  }

  useEffect(() => { load(); }, []);

  function urgencyColor(dateStr: string) {
    const days = differenceInDays(parseISO(dateStr), new Date());
    if (days <= 7)  return "border-red-400/30 bg-red-400/5";
    if (days <= 14) return "border-yellow-400/30 bg-yellow-400/5";
    return "border-white/5 bg-surface-1";
  }

  function urgencyBadge(dateStr: string) {
    const days = differenceInDays(parseISO(dateStr), new Date());
    if (days <= 0)  return <span className="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-red-500/20 text-red-400 border border-red-400/30">Overdue</span>;
    if (days <= 7)  return <span className="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-red-400/10 text-red-400 border border-red-400/20">{days}d</span>;
    if (days <= 14) return <span className="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-yellow-400/10 text-yellow-400 border border-yellow-400/20">{days}d</span>;
    return <span className="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-brand-400/10 text-brand-400 border border-brand-400/20">{days}d</span>;
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Bell size={15} className="text-brand-400" />
          <span className="text-sm font-display font-semibold text-ink-primary">
            Refill Alerts
          </span>
          {alerts.length > 0 && (
            <span className="w-5 h-5 rounded-full bg-red-500 text-white text-[10px] font-mono font-bold flex items-center justify-center">
              {alerts.length}
            </span>
          )}
        </div>
        <div className="flex gap-2">
          <button onClick={scan} disabled={scanning}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono text-brand-400 bg-brand-400/10 border border-brand-400/20 rounded-lg hover:bg-brand-400/20 transition-colors disabled:opacity-50">
            <Zap size={11} className={scanning ? "animate-pulse" : ""} />
            {scanning ? "Scanning..." : "Run scan"}
          </button>
          <button onClick={load}
            className="p-1.5 text-ink-muted hover:text-brand-400 bg-surface-2 border border-white/5 rounded-lg transition-colors">
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* List */}
      <div className="space-y-2">
        {loading && (
          <p className="text-xs text-ink-muted font-mono text-center py-6">Loading alerts...</p>
        )}
        {!loading && alerts.length === 0 && (
          <div className="text-center py-8 space-y-1">
            <Bell size={24} className="text-ink-muted mx-auto" />
            <p className="text-xs text-ink-muted font-mono">No pending refill alerts</p>
          </div>
        )}
        {alerts.map(alert => (
          <div key={alert.id}
            className={clsx("flex items-start justify-between gap-3 p-3 rounded-xl border transition-all", urgencyColor(alert.predicted_refill_date))}>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <p className="text-sm font-body text-ink-primary truncate">
                  {alert.products?.name || `Product #${alert.product_id}`}
                </p>
                {urgencyBadge(alert.predicted_refill_date)}
              </div>
              <div className="flex items-center gap-3 text-[11px] font-mono text-ink-muted">
                <span>Patient: <span className="text-ink-secondary">{alert.users?.patient_id}</span></span>
                <span>Due: <span className="text-ink-secondary">
                  {format(parseISO(alert.predicted_refill_date), "MMM d, yyyy")}
                </span></span>
              </div>
            </div>
            <button onClick={() => dismiss(alert.id)}
              className="p-1.5 text-ink-muted hover:text-red-400 hover:bg-red-400/10 rounded-lg transition-colors flex-shrink-0">
              <X size={13} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
