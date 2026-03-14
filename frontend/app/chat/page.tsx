"use client";
export const dynamic = "force-dynamic";
// app/chat/page.tsx — authenticated, reads real user from Supabase

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, LogOut, User } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import ChatWindow from "@/components/chat/ChatWindow";

export default function ChatPage() {
  const router   = useRouter();
  const supabase = createClient();

  const [patientId,    setPatientId]    = useState<string | null>(null);
  const [patientEmail, setPatientEmail] = useState<string>("");
  const [patientName,  setPatientName]  = useState<string>("Patient");
  const [loading,      setLoading]      = useState(true);

  useEffect(() => {
    async function loadUser() {
      const { data: { user }, error } = await supabase.auth.getUser();
      if (error || !user) {
        router.replace("/auth?return_to=/chat");
        return;
      }
      // Use the Supabase user ID as the patient_id passed to the backend.
      // The backend looks up/creates the patient record by this ID + email.
      setPatientId(user.id);
      setPatientEmail(user.email ?? "");
      setPatientName(user.user_metadata?.full_name ?? user.email?.split("@")[0] ?? "Patient");
      setLoading(false);
    }
    loadUser();
  }, []);

  async function handleLogout() {
    await supabase.auth.signOut();
    router.replace("/auth");
  }

  if (loading) {
    return (
      <div style={{ minHeight: "100dvh", background: "#0a0f0d", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ width: 32, height: 32, borderRadius: "50%", border: "2px solid #1a2820", borderTopColor: "#2dd4a0", animation: "spin .8s linear infinite" }} />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col bg-surface-0">
      <nav className="flex items-center justify-between px-6 py-4 border-b border-white/5 bg-surface-1">
        <div className="flex items-center gap-4">
          <Link href="/" className="text-ink-muted hover:text-ink-primary transition-colors">
            <ArrowLeft size={16} />
          </Link>
          <span style={{ fontFamily: "'Necosmic','Syne',sans-serif", fontSize: 16, color: "#2dd4a0" }}>
            ArogyaX
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7, padding: "5px 12px", borderRadius: 10, background: "#111916", border: "1px solid #1a2820" }}>
            <User size={13} style={{ color: "#2dd4a0" }} />
            <span style={{ fontFamily: "'Sofia Pro','DM Sans',sans-serif", fontSize: 12, color: "#8aada0", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" as const }}>
              {patientName}
            </span>
          </div>
          <button
            onClick={handleLogout}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 12px", borderRadius: 10, background: "transparent", border: "1px solid #1a2820", cursor: "pointer", fontFamily: "'Sofia Pro','DM Sans',sans-serif", fontSize: 12, color: "#4a6b5e", transition: "all .2s" }}
            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.color = "#e8f5f0"; (e.currentTarget as HTMLButtonElement).style.borderColor = "#2dd4a030"; }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.color = "#4a6b5e"; (e.currentTarget as HTMLButtonElement).style.borderColor = "#1a2820"; }}
          >
            <LogOut size={13} /> Log out
          </button>
        </div>
      </nav>

      <div className="flex-1 p-4 max-w-3xl mx-auto w-full" style={{ height: "calc(100vh - 65px)" }}>
        {patientId && (
          <ChatWindow
            patientId={patientId}
            patientEmail={patientEmail}
            patientName={patientName}
          />
        )}
      </div>
    </div>
  );
}

