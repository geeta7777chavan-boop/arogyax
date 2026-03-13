// app/auth/callback/route.ts

import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);

  console.log("[auth/callback] URL:", request.url);
  console.log("[auth/callback] params:", Object.fromEntries(searchParams.entries()));

  const code      = searchParams.get("code");
  const tokenHash = searchParams.get("token_hash");
  const type      = searchParams.get("type");
  const next      = searchParams.get("next") ?? "/chat";

  // ── token_hash flow (Supabase email OTP / newer format) ─────────────────
  if (tokenHash && type) {
    const supabase = await createClient();
    const { error } = await supabase.auth.verifyOtp({
      token_hash: tokenHash,
      type: type as any,
    });

    if (error) {
      console.error("[auth/callback] verifyOtp error:", error.message);
      return NextResponse.redirect(`${origin}/auth?error=auth_callback_failed`);
    }

    // ANY recovery type → always go to reset-password
    if (type === "recovery") {
      return NextResponse.redirect(`${origin}/reset-password`);
    }

    const { data: { user } } = await supabase.auth.getUser();
    if (user) {
      const { data: profile } = await supabase
        .from("profiles").select("role").eq("id", user.id).single();
      const role = profile?.role ?? "patient";
      return NextResponse.redirect(`${origin}${role === "admin" ? "/admin" : next}`);
    }
  }

  // ── PKCE code flow ───────────────────────────────────────────────────────
  if (code) {
    const supabase = await createClient();
    const { data, error } = await supabase.auth.exchangeCodeForSession(code);

    if (error) {
      console.error("[auth/callback] exchangeCodeForSession error:", error.message);
      return NextResponse.redirect(`${origin}/auth?error=auth_callback_failed`);
    }

    console.log("[auth/callback] session user email:", data?.user?.email);
    console.log("[auth/callback] next param:", next);

    // next param set correctly → trust it
    if (next === "/reset-password") {
      return NextResponse.redirect(`${origin}/reset-password`);
    }

    // next param missing but this is a recovery session — detect via user metadata
    // Supabase sets recovery_sent_at on the user when a reset is initiated
    const user = data?.user;
    if (user?.recovery_sent_at) {
      console.log("[auth/callback] detected recovery via recovery_sent_at, redirecting to /reset-password");
      return NextResponse.redirect(`${origin}/reset-password`);
    }

    // Regular signup confirmation
    if (user) {
      const { data: profile } = await supabase
        .from("profiles").select("role").eq("id", user.id).single();
      const role = profile?.role ?? "patient";
      return NextResponse.redirect(`${origin}${role === "admin" ? "/admin" : next}`);
    }
  }

  // ── Hash fragment flow (implicit / legacy) ───────────────────────────────
  return new NextResponse(
    `<!DOCTYPE html>
<html>
<head><title>Redirecting…</title></head>
<body>
<script>
  const params = new URLSearchParams(window.location.hash.substring(1));
  const type   = params.get("type");
  const at     = params.get("access_token");
  const rt     = params.get("refresh_token") || "";
  if (type === "recovery" && at) {
    sessionStorage.setItem("sb_access_token", at);
    sessionStorage.setItem("sb_refresh_token", rt);
    window.location.replace("/reset-password");
  } else if (at) {
    window.location.replace("/chat");
  } else {
    console.log("[auth/callback] no token found in hash:", window.location.hash);
    window.location.replace("/auth?error=auth_callback_failed");
  }
</script>
<p>Redirecting…</p>
</body>
</html>`,
    { headers: { "Content-Type": "text/html" } }
  );
}