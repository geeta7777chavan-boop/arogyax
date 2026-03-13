"use client";
// app/admin/page.tsx
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Pill, Package, Bell, Shield, BarChart2, LogOut } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import AnalyticsDashboard from "@/components/admin/AnalyticsDashboard";
import InventoryTable  from "@/components/admin/InventoryTable";
import AlertsPanel     from "@/components/admin/AlertsPanel";
import DecisionLedger  from "@/components/admin/DecisionLedger";
import AdminNotificationPopup from "@/components/admin/AdminNotificationPopup";
import { clsx } from "clsx";

const TABS = [
  { id: "analytics", label: "Analytics",      icon: <BarChart2 size={14} /> },
  { id: "inventory", label: "Inventory",       icon: <Package size={14} /> },
  { id: "alerts",    label: "Refill Alerts",   icon: <Bell size={14} /> },
  { id: "decisions", label: "Decision Ledger", icon: <Shield size={14} /> },
] as const;

type Tab = typeof TABS[number]["id"];

export default function AdminPage() {
  const [tab, setTab] = useState<Tab>("inventory");
  const router = useRouter();
  const supabase = createClient();

  function handleViewInventory() {
    setTab("inventory");
  }

  async function handleLogout() {
    await supabase.auth.signOut();
    router.replace("/auth");
  }

  return (
    <div className="min-h-screen bg-surface-0 flex flex-col">
      {/* Top nav */}
      <nav className="flex items-center justify-between px-6 py-4 border-b border-white/5 bg-surface-1 shrink-0">
        <div className="flex items-center gap-4">
          <Link href="/" className="text-ink-muted hover:text-ink-primary transition-colors">
            <ArrowLeft size={16} />
          </Link>
          <div className="flex items-center gap-2">
            <Pill size={16} className="text-brand-400" />
            <span className="font-display font-semibold text-ink-primary text-sm">Admin Dashboard</span>
          </div>
        </div>
        <button
          onClick={handleLogout}
          className="flex items-center gap-2 px-3 py-1.5 bg-surface-2 border border-white/5 rounded-lg text-xs text-ink-muted hover:text-red-400 hover:border-red-400/30 transition-all"
        >
          <LogOut size={14} />
          Log out
        </button>
      </nav>

      <div className="flex-1 max-w-6xl mx-auto w-full p-6 flex flex-col gap-6">
        {/* Tab bar */}
        <div className="flex gap-1 bg-surface-1 border border-white/5 rounded-xl p-1 w-fit">
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={clsx(
                "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-body transition-all",
                tab === t.id
                  ? "bg-brand-600 text-white shadow-md"
                  : "text-ink-secondary hover:text-ink-primary hover:bg-surface-2"
              )}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1">
          {tab === "analytics" && <AnalyticsDashboard />}
          {tab === "inventory" && <InventoryTable />}
          {tab === "alerts"    && <AlertsPanel />}
          {tab === "decisions" && <DecisionLedger />}
        </div>
      </div>

      {/* Low Stock Notification Popup */}
      <AdminNotificationPopup 
        threshold={10} 
        autoCheckInterval={30000}
        onViewInventory={handleViewInventory}
      />
    </div>
  );
}
