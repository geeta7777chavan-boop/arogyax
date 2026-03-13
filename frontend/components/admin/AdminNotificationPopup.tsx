"use client";
// components/admin/AdminNotificationPopup.tsx

import { useState, useEffect } from "react";
import { getLowStockAlerts } from "@/lib/api";
import type { LowStockAlert } from "@/types";
import { AlertTriangle, X, Package, Bell, Settings } from "lucide-react";
import { clsx } from "clsx";

interface AdminNotificationPopupProps {
  threshold?: number;
  autoCheckInterval?: number; // in milliseconds, default 30000 (30 seconds)
  onViewInventory?: () => void;
}

export default function AdminNotificationPopup({ 
  threshold = 10, 
  autoCheckInterval = 30000,
  onViewInventory 
}: AdminNotificationPopupProps) {
  const [alerts, setAlerts] = useState<LowStockAlert[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [hasNewAlert, setHasNewAlert] = useState(false);
  const [lastCheck, setLastCheck] = useState<Date>(new Date());

  async function checkAlerts() {
    try {
      const { alerts } = await getLowStockAlerts(threshold);
      const newAlerts = alerts;
      
      // Check if there are new critical alerts
      const criticalCount = newAlerts.filter(a => a.severity === "critical").length;
      const previousCriticalCount = alerts.filter(a => a.severity === "critical").length;
      
      setAlerts(newAlerts);
      setLastCheck(new Date());
      
      // If there are critical alerts and we haven't shown them yet, trigger popup
      if (criticalCount > 0 && !isOpen) {
        setHasNewAlert(true);
        setIsOpen(true);
      }
    } catch (error: any) {
      // Network errors mean backend is unavailable - don't show error, just skip
      if (error.code === 'ERR_NETWORK' || error.message?.includes('Network Error')) {
        console.log("Backend unavailable - skipping alert check");
        return;
      }
      console.error("Failed to check low stock alerts:", error);
    }
  }

  // Auto-check for alerts
  useEffect(() => {
    checkAlerts(); // Initial check
    
    const interval = setInterval(checkAlerts, autoCheckInterval);
    return () => clearInterval(interval);
  }, [threshold, autoCheckInterval]);

  const criticalAlerts = alerts.filter(a => a.severity === "critical");
  const warningAlerts = alerts.filter(a => a.severity === "warning");
  const totalCount = alerts.length;

  function handleClose() {
    setIsOpen(false);
    setHasNewAlert(false);
  }

  if (!isOpen && !hasNewAlert) {
    // Show floating button when popup is closed
    return (
      <div className="fixed bottom-6 right-6 z-50">
        <button
          onClick={() => setIsOpen(true)}
          className={clsx(
            "relative flex items-center gap-2 px-4 py-3 rounded-xl shadow-lg transition-all",
            totalCount > 0 
              ? "bg-red-500 hover:bg-red-600 text-white animate-pulse" 
              : "bg-brand-600 hover:bg-brand-700 text-white"
          )}
        >
          {totalCount > 0 ? (
            <>
              <AlertTriangle size={18} />
              <span className="font-medium text-sm">Low Stock: {totalCount}</span>
              <span className="absolute -top-2 -right-2 w-5 h-5 bg-white text-red-500 rounded-full text-xs font-bold flex items-center justify-center">
                {totalCount}
              </span>
            </>
          ) : (
            <>
              <Bell size={18} />
              <span className="font-medium text-sm">Stock OK</span>
            </>
          )}
        </button>
      </div>
    );
  }

  // Show popup
  return (
    <div className="fixed bottom-6 right-6 z-50 w-96">
      {/* Popup Card */}
      <div className="bg-surface-1 border border-white/10 rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className={clsx(
          "flex items-center justify-between px-4 py-3",
          criticalAlerts.length > 0 ? "bg-red-500/20" : "bg-yellow-500/20"
        )}>
          <div className="flex items-center gap-2">
            <AlertTriangle size={18} className={criticalAlerts.length > 0 ? "text-red-400" : "text-yellow-400"} />
            <span className="font-semibold text-sm text-ink-primary">
              Low Stock Alert
            </span>
            {totalCount > 0 && (
              <span className={clsx(
                "px-2 py-0.5 rounded-full text-xs font-bold",
                criticalAlerts.length > 0 
                  ? "bg-red-500 text-white" 
                  : "bg-yellow-500 text-black"
              )}>
                {totalCount}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={checkAlerts}
              className="p-1.5 text-ink-muted hover:text-brand-400 rounded-lg hover:bg-white/5 transition-colors"
              title="Refresh"
            >
              <Settings size={14} />
            </button>
            <button
              onClick={handleClose}
              className="p-1.5 text-ink-muted hover:text-ink-primary rounded-lg hover:bg-white/5 transition-colors"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="max-h-80 overflow-y-auto">
          {totalCount === 0 ? (
            <div className="p-6 text-center">
              <Bell size={32} className="text-brand-400 mx-auto mb-2" />
              <p className="text-sm text-ink-secondary">All stock levels are healthy!</p>
              <p className="text-xs text-ink-muted mt-1">
                Last checked: {lastCheck.toLocaleTimeString()}
              </p>
            </div>
          ) : (
            <div className="p-3 space-y-2">
              {/* Critical Section */}
              {criticalAlerts.length > 0 && (
                <div className="space-y-1">
                  <p className="text-xs font-bold text-red-400 px-1">CRITICAL</p>
                  {criticalAlerts.slice(0, 3).map(alert => (
                    <div key={alert.product_id} 
                      className="flex items-center gap-2 p-2 rounded-lg bg-red-500/10 border border-red-500/20">
                      <Package size={14} className="text-red-400 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-ink-primary truncate font-medium">
                          {alert.name}
                        </p>
                        <p className="text-[10px] text-red-400 font-mono">
                          Stock: {alert.stock_quantity} / {alert.threshold}
                        </p>
                      </div>
                    </div>
                  ))}
                  {criticalAlerts.length > 3 && (
                    <p className="text-[10px] text-ink-muted px-1">
                      +{criticalAlerts.length - 3} more critical
                    </p>
                  )}
                </div>
              )}

              {/* Warning Section */}
              {warningAlerts.length > 0 && (
                <div className="space-y-1">
                  <p className="text-xs font-bold text-yellow-400 px-1">WARNING</p>
                  {warningAlerts.slice(0, 2).map(alert => (
                    <div key={alert.product_id} 
                      className="flex items-center gap-2 p-2 rounded-lg bg-yellow-500/10 border border-yellow-500/20">
                      <Package size={14} className="text-yellow-400 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-ink-primary truncate font-medium">
                          {alert.name}
                        </p>
                        <p className="text-[10px] text-yellow-400 font-mono">
                          Stock: {alert.stock_quantity} / {alert.threshold}
                        </p>
                      </div>
                    </div>
                  ))}
                  {warningAlerts.length > 2 && (
                    <p className="text-[10px] text-ink-muted px-1">
                      +{warningAlerts.length - 2} more warning
                    </p>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        {totalCount > 0 && (
          <div className="px-4 py-3 bg-surface-2 border-t border-white/5">
            <button
              onClick={() => {
                handleClose();
                onViewInventory?.();
              }}
              className="w-full py-2 px-4 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium rounded-lg transition-colors"
            >
              View Inventory
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
