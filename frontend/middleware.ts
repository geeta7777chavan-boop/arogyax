// middleware.ts  (root of frontend — sits next to app/)
// Runs on every request before page renders.
// 1. Refreshes the Supabase session token (keeps "remember me" alive)
// 2. Enforces role-based access:
//    - /chat   → patient only
//    - /admin  → admin only
//    - /auth   → redirect to /chat or /admin if already logged in

import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import type { SupabaseClient } from "@supabase/supabase-js";

export async function middleware(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet: { name: string; value: string; options?: CookieOptions }[]) {
          // Write cookies to both the request (for downstream) and the response
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value)
          );
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          );
        },
      },
    }
  ) as SupabaseClient;

  // Refresh session — MUST call getUser() not getSession() per Supabase docs
  const { data: { user } } = await supabase.auth.getUser();

  const { pathname } = request.nextUrl;

  // ── If logged in and visiting /auth → redirect to their home ─────────────
  if (user && pathname.startsWith("/auth")) {
    // Fetch role from profiles table
    const { data: profile } = await supabase
      .from("profiles")
      .select("role")
      .eq("id", user.id)
      .single();

    const role = profile?.role ?? "patient";
    const dest = role === "admin" ? "/admin" : "/chat";
    return NextResponse.redirect(new URL(dest, request.url));
  }

  // ── Protected routes ──────────────────────────────────────────────────────
  const protectedPaths = ["/chat", "/admin"];
  const isProtected = protectedPaths.some(p => pathname.startsWith(p));

  if (isProtected && !user) {
    // Not logged in — send to auth with a return_to hint
    const loginUrl = new URL("/auth", request.url);
    loginUrl.searchParams.set("return_to", pathname);
    return NextResponse.redirect(loginUrl);
  }

  // ── Role enforcement ──────────────────────────────────────────────────────
  if (isProtected && user) {
    const { data: profile } = await supabase
      .from("profiles")
      .select("role")
      .eq("id", user.id)
      .single();

    const role = profile?.role ?? "patient";

    // Admin trying to access /chat — redirect to /admin
    if (pathname.startsWith("/chat") && role === "admin") {
      return NextResponse.redirect(new URL("/admin", request.url));
    }

    // Patient trying to access /admin — redirect to /chat
    if (pathname.startsWith("/admin") && role !== "admin") {
      return NextResponse.redirect(new URL("/chat", request.url));
    }
  }

  return supabaseResponse;
}

export const config = {
  matcher: [
    // Match all paths except static files, images, and Next.js internals
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};