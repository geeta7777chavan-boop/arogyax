"use client";
// app/auth/page.tsx — ArogyaX · Login / Signup / Forgot Password

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Eye, EyeOff, ArrowRight, Loader2, CheckCircle2, AlertCircle, Mail, ArrowLeft } from "lucide-react";
import { createClient } from "@/lib/supabase/client";

type Mode = "login" | "signup" | "forgot";

/* ─── Forgot success screen (self-contained with resend + cooldown) ──── */
function ForgotSuccessScreen({
  email, onBack,
}: { email: string; onBack: () => void }) {
  const supabase = createClient();
  const COOLDOWN = 60; // seconds — matches Supabase rate limit

  const [resendState, setResendState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [countdown,   setCountdown]   = useState(0);
  const [errMsg,      setErrMsg]      = useState("");

  // Tick countdown
  useEffect(() => {
    if (countdown <= 0) return;
    const t = setTimeout(() => setCountdown(c => c - 1), 1000);
    return () => clearTimeout(t);
  }, [countdown]);

  async function handleResend() {
    if (countdown > 0 || resendState === "sending") return;
    setResendState("sending");
    setErrMsg("");
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/auth/callback?next=/reset-password`,
      });
      if (error) throw error;
      setResendState("sent");
      setCountdown(COOLDOWN);
      // After 4s reset label back to idle (but keep countdown running)
      setTimeout(() => setResendState("idle"), 4000);
    } catch (err: any) {
      setResendState("error");
      setErrMsg(err?.message ?? "Failed to resend. Please try again.");
      setTimeout(() => setResendState("idle"), 4000);
    }
  }

  const btnDisabled = countdown > 0 || resendState === "sending";

  return (
    <div style={{ textAlign: "center", padding: "8px 0" }}>
      <div style={{ width: 56, height: 56, borderRadius: "50%", background: "#2dd4a012", border: "1px solid #2dd4a030", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 24px", color: "#2dd4a0" }}>
        <Mail size={24} />
      </div>
      <h2 style={{ fontFamily: "'Syne',sans-serif", fontWeight: 800, fontSize: 22, color: "#e8f5f0", marginBottom: 16, letterSpacing: "-.02em" }}>
        Check your inbox
      </h2>
      <p style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontSize: 14, color: "#5a8070", lineHeight: 1.75 }}>
        If an account exists for <strong style={{ color: "#8aada0" }}>{email}</strong>, a password reset link has been sent.
      </p>
      <p style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontSize: 13, color: "#3d5e50", lineHeight: 1.6, marginTop: 10 }}>
        Please check your inbox and spam folder.<br />
        The link expires in <strong style={{ color: "#6a9080" }}>1 hour</strong>.
      </p>

      {/* Resend box */}
      <div style={{ marginTop: 28, padding: "16px", borderRadius: 12, background: "#0c1710", border: `1px solid ${resendState === "sent" ? "#2dd4a030" : resendState === "error" ? "#ef444430" : "#1a2820"}`, transition: "border-color .3s" }}>
        {resendState === "sent" ? (
          <p style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontSize: 13, color: "#2dd4a0", display: "flex", alignItems: "center", justifyContent: "center", gap: 7, margin: 0 }}>
            <CheckCircle2 size={14} /> Link resent! Check your inbox.
          </p>
        ) : resendState === "error" ? (
          <p style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontSize: 13, color: "#fca5a5", display: "flex", alignItems: "center", justifyContent: "center", gap: 7, margin: 0 }}>
            <AlertCircle size={14} /> {errMsg}
          </p>
        ) : (
          <>
            <p style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontSize: 12, color: "#3d5e50", marginBottom: 10 }}>
              Didn't receive it?
            </p>
            <button
              onClick={handleResend}
              disabled={btnDisabled}
              style={{
                fontFamily: "'Plus Jakarta Sans',sans-serif", fontSize: 13, fontWeight: 600,
                color: btnDisabled ? "#2a4038" : "#2dd4a0",
                background: "none", border: "none",
                cursor: btnDisabled ? "not-allowed" : "pointer",
                display: "inline-flex", alignItems: "center", gap: 7,
                transition: "color .2s",
              }}
            >
              {resendState === "sending"
                ? <><Loader2 size={13} style={{ animation: "spin .8s linear infinite" }} /> Sending…</>
                : countdown > 0
                  ? `Resend in ${countdown}s`
                  : "Resend reset link"
              }
            </button>
          </>
        )}
      </div>

      <button onClick={onBack}
        style={{ marginTop: 20, display: "flex", alignItems: "center", gap: 6, fontFamily: "'Plus Jakarta Sans',sans-serif", fontSize: 13, color: "#4a6b5e", background: "none", border: "none", cursor: "pointer", margin: "20px auto 0", transition: "color .2s" }}
        onMouseEnter={e => (e.currentTarget.style.color = "#2dd4a0")}
        onMouseLeave={e => (e.currentTarget.style.color = "#4a6b5e")}
      >
        <ArrowLeft size={13} /> Back to Log In
      </button>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

/* ─── Reusable input field ──────────────────────────────────────────────── */
function Field({
  label, type = "text", value, onChange, placeholder, autoComplete, error,
}: {
  label: string; type?: string; value: string;
  onChange: (v: string) => void; placeholder?: string;
  autoComplete?: string; error?: string;
}) {
  const [show, setShow] = useState(false);
  const isPass = type === "password";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
      <label style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontSize: 12, color: "#6a9080", fontWeight: 600, letterSpacing: ".04em" }}>
        {label}
      </label>
      <div style={{ position: "relative" }}>
        <input
          type={isPass ? (show ? "text" : "password") : type}
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          autoComplete={autoComplete}
          style={{
            width: "100%", boxSizing: "border-box" as const,
            padding: isPass ? "12px 44px 12px 16px" : "12px 16px",
            borderRadius: 12,
            background: "#0c1710",
            border: `1px solid ${error ? "#ef4444" : "#1a2820"}`,
            color: "#e8f5f0",
            fontFamily: "'Plus Jakarta Sans',sans-serif",
            fontSize: 14, fontWeight: 400,
            outline: "none",
            transition: "border-color .2s",
          }}
          onFocus={e => { if (!error) e.target.style.borderColor = "#2dd4a040"; }}
          onBlur={e  => { if (!error) e.target.style.borderColor = error ? "#ef4444" : "#1a2820"; }}
        />
        {isPass && (
          <button type="button" onClick={() => setShow(s => !s)}
            style={{ position: "absolute", right: 14, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "#3d5e50", padding: 0, display: "flex" }}>
            {show ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
        )}
      </div>
      {error && <p style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontSize: 11, color: "#ef4444", marginTop: 2 }}>{error}</p>}
    </div>
  );
}

/* ─── Password strength indicator ──────────────────────────────────────── */
function PasswordStrength({ password }: { password: string }) {
  if (!password) return null;

  const checks = [
    { label: "8+ characters",       pass: password.length >= 8           },
    { label: "Uppercase letter",    pass: /[A-Z]/.test(password)         },
    { label: "Lowercase letter",    pass: /[a-z]/.test(password)         },
    { label: "Number or symbol",    pass: /[\d\W]/.test(password)        },
  ];
  const score = checks.filter(c => c.pass).length;
  const levels = ["", "Weak", "Fair", "Good", "Strong"];
  const colors = ["", "#ef4444", "#f59e0b", "#3b82f6", "#2dd4a0"];

  return (
    <div style={{ marginTop: 8 }}>
      {/* Bar */}
      <div style={{ display: "flex", gap: 4, marginBottom: 8 }}>
        {[1,2,3,4].map(i => (
          <div key={i} style={{
            flex: 1, height: 3, borderRadius: 99,
            background: i <= score ? colors[score] : "#1a2820",
            transition: "background .3s",
          }} />
        ))}
      </div>
      {/* Label + checklist */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div style={{ display: "flex", flexWrap: "wrap" as const, gap: "4px 12px" }}>
          {checks.map(c => (
            <span key={c.label} style={{
              fontFamily: "'Plus Jakarta Sans',sans-serif",
              fontSize: 10.5, fontWeight: 500,
              color: c.pass ? "#2dd4a0" : "#3d5e50",
              display: "flex", alignItems: "center", gap: 4,
              transition: "color .2s",
            }}>
              <span style={{ fontSize: 10 }}>{c.pass ? "✓" : "·"}</span>
              {c.label}
            </span>
          ))}
        </div>
        {score > 0 && (
          <span style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontSize: 10.5, fontWeight: 700, color: colors[score], flexShrink: 0, marginLeft: 8 }}>
            {levels[score]}
          </span>
        )}
      </div>
    </div>
  );
}

/* ─── Main Auth component ───────────────────────────────────────────────── */
export default function AuthPage() {
  const router       = useRouter();
  const searchParams = useSearchParams();
  const supabase     = createClient();

  const initMode = (searchParams.get("mode") as Mode) ?? "login";
  const returnTo = searchParams.get("return_to") ?? "/chat";
  const urlError = searchParams.get("error");

  const [mode,      setMode]      = useState<Mode>(initMode);
  const [name,      setName]      = useState("");
  const [email,     setEmail]     = useState("");
  const [password,  setPassword]  = useState("");
  const [loading,   setLoading]   = useState(false);
  const [success,   setSuccess]   = useState<"signup" | "forgot" | null>(null);
  const [errors,    setErrors]    = useState<Record<string, string>>({});
  const [globalErr, setGlobalErr] = useState(
    urlError === "auth_callback_failed" ? "Email confirmation failed. Please try again." : ""
  );

  function switchMode(m: Mode) {
    setMode(m); setErrors({}); setGlobalErr(""); setSuccess(null);
  }

  /* ── Validation ─────────────────────────────────────────────────────── */
  function validate() {
    const e: Record<string, string> = {};
    if (mode === "signup" && !name.trim())
      e.name = "Please enter your name";
    if (!email.match(/^[^\s@]+@[^\s@]+\.[^\s@]+$/))
      e.email = "Enter a valid email address";
    if (mode !== "forgot" && password.length < 8)
      e.password = mode === "signup" ? "Password must be at least 8 characters" : "Incorrect email or password";
    return e;
  }

  /* ── Submit ─────────────────────────────────────────────────────────── */
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setGlobalErr("");
    const errs = validate();
    setErrors(errs);
    if (Object.keys(errs).length) return;

    setLoading(true);
    try {

      /* ── Forgot password ── */
      if (mode === "forgot") {
        // Always show the same success screen regardless of whether the email
        // exists — prevents user enumeration attacks.
        await supabase.auth.resetPasswordForEmail(email, {
          redirectTo: `${window.location.origin}/auth/callback?next=/reset-password`,
        });
        setSuccess("forgot");
        return;
      }

      /* ── Sign up ── */
      if (mode === "signup") {
        const { data: signUpData, error } = await supabase.auth.signUp({
          email, password,
          options: {
            data: { full_name: name.trim() },
            emailRedirectTo: `${window.location.origin}/auth/callback?next=${returnTo}`,
          },
        });
        if (error) throw error;

        // When email confirmations are OFF, Supabase silently returns a fake
        // session for duplicate emails instead of throwing an error.
        // Detect this: a real new user has an empty identities array.
        if (
          signUpData?.user &&
          signUpData.user.identities !== undefined &&
          signUpData.user.identities.length === 0
        ) {
          setGlobalErr("An account with this email already exists. Try logging in.");
          return;
        }

        setSuccess("signup");
        return;
      }

      /* ── Log in ── */
      const { data, error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) throw error;

      const { data: profile } = await supabase
        .from("profiles").select("role").eq("id", data.user.id).single();
      const role = profile?.role ?? "patient";
      router.replace(role === "admin" ? "/admin" : returnTo);

    } catch (err: any) {
      const msg: string = err?.message ?? "Something went wrong";
      if (msg.includes("Invalid login credentials"))
        setGlobalErr("Incorrect email or password.");
      else if (msg.includes("already registered"))
        setGlobalErr("An account with this email already exists. Try logging in.");
      else if (msg.includes("Email not confirmed"))
        setGlobalErr("Please confirm your email before logging in.");
      else
        setGlobalErr(msg);
    } finally {
      setLoading(false);
    }
  }

  /* ── Signup success screen ─────────────────────────────────────────── */
  if (success === "signup") {
    return (
      <Wrapper>
        <div style={{ textAlign: "center", padding: "8px 0" }}>
          <div style={{ width: 56, height: 56, borderRadius: "50%", background: "#2dd4a012", border: "1px solid #2dd4a030", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 24px", color: "#2dd4a0" }}>
            <CheckCircle2 size={26} />
          </div>
          <h2 style={{ fontFamily: "'Syne',sans-serif", fontWeight: 800, fontSize: 22, color: "#e8f5f0", marginBottom: 12, letterSpacing: "-.02em" }}>
            Check your email
          </h2>
          <p style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontSize: 14, color: "#5a8070", lineHeight: 1.7 }}>
            We sent a confirmation link to<br />
            <strong style={{ color: "#8aada0" }}>{email}</strong>.<br /><br />
            Click the link to activate your account and get started.
          </p>
          <button onClick={() => switchMode("login")}
            style={{ marginTop: 32, fontFamily: "'Plus Jakarta Sans',sans-serif", fontSize: 13, color: "#2dd4a0", background: "none", border: "none", cursor: "pointer", textDecoration: "underline" }}>
            Back to Log In
          </button>
        </div>
      </Wrapper>
    );
  }

  /* ── Forgot password success screen ───────────────────────────────── */
  if (success === "forgot") {
    return (
      <Wrapper>
        <ForgotSuccessScreen email={email} onBack={() => switchMode("login")} />
      </Wrapper>
    );
  }

  /* ── Forgot password form ──────────────────────────────────────────── */
  if (mode === "forgot") {
    return (
      <Wrapper>
        {/* Back link */}
        <button onClick={() => switchMode("login")}
          style={{ display: "flex", alignItems: "center", gap: 7, fontFamily: "'Plus Jakarta Sans',sans-serif", fontSize: 13, color: "#4a6b5e", background: "none", border: "none", cursor: "pointer", marginBottom: 28, padding: 0, transition: "color .2s" }}
          onMouseEnter={e => (e.currentTarget.style.color = "#2dd4a0")}
          onMouseLeave={e => (e.currentTarget.style.color = "#4a6b5e")}
        >
          <ArrowLeft size={14} /> Back to Log In
        </button>

        {/* Heading */}
        <div style={{ marginBottom: 28 }}>
          <h1 style={{ fontFamily: "'Syne',sans-serif", fontWeight: 800, fontSize: 24, color: "#e8f5f0", letterSpacing: "-.03em", marginBottom: 8 }}>
            Reset your password
          </h1>
          <p style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontSize: 13, color: "#4a6b5e", lineHeight: 1.6 }}>
            Enter your email and we'll send you a link to reset your password. The link expires in 1 hour.
          </p>
        </div>

        {/* Error */}
        {globalErr && (
          <div style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "12px 14px", borderRadius: 10, background: "#1a0c0c", border: "1px solid #ef444430", marginBottom: 22 }}>
            <AlertCircle size={15} style={{ color: "#ef4444", flexShrink: 0, marginTop: 1 }} />
            <p style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontSize: 13, color: "#fca5a5", margin: 0 }}>{globalErr}</p>
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <Field label="Email address" type="email" value={email} onChange={setEmail}
            placeholder="you@example.com" autoComplete="email" error={errors.email} />

          <button type="submit" disabled={loading}
            style={{
              marginTop: 4, display: "flex", alignItems: "center", justifyContent: "center", gap: 9,
              padding: "13px 0", borderRadius: 13,
              background: loading ? "#0d3326" : "linear-gradient(135deg,#059669,#2dd4a0)",
              color: "#051a0e", border: "none",
              fontFamily: "'Syne',sans-serif", fontWeight: 700, fontSize: 15,
              cursor: loading ? "not-allowed" : "pointer",
              transition: "all .2s", boxShadow: loading ? "none" : "0 4px 24px #2dd4a028",
            }}>
            {loading
              ? <><Loader2 size={16} style={{ animation: "spin .8s linear infinite" }} /> Sending link…</>
              : <>Send Reset Link <ArrowRight size={15} /></>
            }
          </button>
        </form>

        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </Wrapper>
    );
  }

  /* ── Main login / signup form ──────────────────────────────────────── */
  return (
    <Wrapper>
      {/* Tab toggle */}
      <div style={{ display: "flex", background: "#0c1710", borderRadius: 12, padding: 4, marginBottom: 32, border: "1px solid #1a2820" }}>
        {(["login", "signup"] as Mode[]).map(m => (
          <button key={m} onClick={() => switchMode(m)}
            style={{
              flex: 1, padding: "9px 0", borderRadius: 9, border: "none",
              fontFamily: "'Plus Jakarta Sans',sans-serif",
              fontSize: 13, fontWeight: 600, cursor: "pointer",
              transition: "all .2s",
              background: mode === m ? "#1a2820" : "transparent",
              color: mode === m ? "#e8f5f0" : "#3d5e50",
              letterSpacing: ".02em",
            }}>
            {m === "login" ? "Log In" : "Sign Up"}
          </button>
        ))}
      </div>

      {/* Heading */}
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontFamily: "'Syne',sans-serif", fontWeight: 800, fontSize: 24, color: "#e8f5f0", letterSpacing: "-.03em", marginBottom: 6 }}>
          {mode === "login" ? "Welcome back" : "Create your account"}
        </h1>
        <p style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontSize: 13, color: "#4a6b5e" }}>
          {mode === "login"
            ? "Sign in to continue to your pharmacy dashboard."
            : "Join ArogyaX for smarter, safer pharmacy care."}
        </p>
      </div>

      {/* Global error */}
      {globalErr && (
        <div style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "12px 14px", borderRadius: 10, background: "#1a0c0c", border: "1px solid #ef444430", marginBottom: 22 }}>
          <AlertCircle size={15} style={{ color: "#ef4444", flexShrink: 0, marginTop: 1 }} />
          <p style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontSize: 13, color: "#fca5a5", margin: 0 }}>{globalErr}</p>
        </div>
      )}

      {/* Form */}
      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        {mode === "signup" && (
          <Field label="Full Name" value={name} onChange={setName}
            placeholder="Arjun Sharma" autoComplete="name" error={errors.name} />
        )}
        <Field label="Email" type="email" value={email} onChange={setEmail}
          placeholder="you@example.com" autoComplete="email" error={errors.email} />

        <div>
          <Field label="Password" type="password" value={password} onChange={setPassword}
            placeholder={mode === "signup" ? "Min. 8 characters" : "Your password"}
            autoComplete={mode === "signup" ? "new-password" : "current-password"}
            error={errors.password} />
          {/* Show strength meter only on signup */}
          {mode === "signup" && <PasswordStrength password={password} />}
        </div>

        {/* Remember me / forgot — login only */}
        {mode === "login" && (
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: -6 }}>
            <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
              <input type="checkbox" defaultChecked style={{ accentColor: "#2dd4a0" }} />
              <span style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontSize: 12, color: "#4a6b5e" }}>
                Remember me for 30 days
              </span>
            </label>
            <button type="button" onClick={() => switchMode("forgot")}
              style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontSize: 12, color: "#2dd4a0", background: "none", border: "none", cursor: "pointer", transition: "opacity .2s" }}
              onMouseEnter={e => (e.currentTarget.style.opacity = ".7")}
              onMouseLeave={e => (e.currentTarget.style.opacity = "1")}
            >
              Forgot password?
            </button>
          </div>
        )}

        {/* Submit */}
        <button type="submit" disabled={loading}
          style={{
            marginTop: 4, display: "flex", alignItems: "center", justifyContent: "center", gap: 9,
            padding: "13px 0", borderRadius: 13,
            background: loading ? "#0d3326" : "linear-gradient(135deg,#059669,#2dd4a0)",
            color: "#051a0e", border: "none",
            fontFamily: "'Syne',sans-serif", fontWeight: 700, fontSize: 15,
            cursor: loading ? "not-allowed" : "pointer",
            transition: "all .2s", boxShadow: loading ? "none" : "0 4px 24px #2dd4a028",
          }}>
          {loading
            ? <><Loader2 size={16} style={{ animation: "spin .8s linear infinite" }} /> {mode === "login" ? "Signing in…" : "Creating account…"}</>
            : <>{mode === "login" ? "Log In" : "Create Account"} <ArrowRight size={15} /></>
          }
        </button>
      </form>

      {/* Footer switch */}
      <p style={{ textAlign: "center", fontFamily: "'Plus Jakarta Sans',sans-serif", fontSize: 13, color: "#3d5e50", marginTop: 24 }}>
        {mode === "login" ? "Don't have an account? " : "Already have an account? "}
        <button onClick={() => switchMode(mode === "login" ? "signup" : "login")}
          style={{ color: "#2dd4a0", background: "none", border: "none", cursor: "pointer", fontWeight: 600, fontFamily: "'Plus Jakarta Sans',sans-serif", fontSize: 13 }}>
          {mode === "login" ? "Sign Up" : "Log In"}
        </button>
      </p>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        input::placeholder { color: #2a3e34; }
        input:-webkit-autofill {
          -webkit-box-shadow: 0 0 0 40px #0c1710 inset !important;
          -webkit-text-fill-color: #e8f5f0 !important;
        }
      `}</style>
    </Wrapper>
  );
}

/* ─── Layout wrapper ────────────────────────────────────────────────────── */
function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ minHeight: "100dvh", background: "#0a0f0d", display: "flex", alignItems: "center", justifyContent: "center", padding: "32px 16px", position: "relative", overflow: "hidden" }}>
      <div style={{ position: "fixed", inset: 0, pointerEvents: "none" }}>
        <div style={{ position: "absolute", width: 500, height: 500, borderRadius: "50%", filter: "blur(90px)", background: "radial-gradient(circle,#0d4430 0%,transparent 65%)", top: -160, left: -140, opacity: .45 }} />
        <div style={{ position: "absolute", width: 360, height: 360, borderRadius: "50%", filter: "blur(80px)", background: "radial-gradient(circle,#064e3b 0%,transparent 65%)", bottom: -100, right: -80, opacity: .35 }} />
      </div>

      <div style={{ position: "relative", zIndex: 1, width: "100%", maxWidth: 420 }}>
        <Link href="/" style={{ display: "block", textAlign: "center", marginBottom: 32, textDecoration: "none" }}>
          <span style={{ fontFamily: "'Necosmic','Syne',sans-serif", fontSize: 28, background: "linear-gradient(148deg,#e8f5f0 8%,#2dd4a0 46%,#059669 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" }}>
            ArogyaX
          </span>
        </Link>

        <div style={{ background: "#0e1812", border: "1px solid #1a2820", borderRadius: 20, padding: "36px 32px", boxShadow: "0 24px 80px #00000050" }}>
          {children}
        </div>

        <p style={{ textAlign: "center", marginTop: 20, fontFamily: "'Plus Jakarta Sans',sans-serif", fontSize: 11, color: "#2a3e34" }}>
          Trusted Care, Always There · ArogyaX © 2026
        </p>
      </div>

      <style>{`@import url('https://fonts.cdnfonts.com/css/necosmic'); @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');`}</style>
    </div>
  );
}