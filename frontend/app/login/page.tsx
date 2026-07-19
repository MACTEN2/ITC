"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError, getCurrentUser, getToken, login, setToken } from "@/lib/api";

/**
 * The Gateway -- credential capture, JWT storage, and role-based redirect.
 *
 * State management:
 *   - `username` / `password`: controlled form inputs.
 *   - `isSubmitting`: disables the form and swaps the button label while the
 *     login + profile-fetch round trip is in flight.
 *   - `error`: last request failure, surfaced inline; cleared on every new
 *     submit attempt so a stale error doesn't linger after a retry.
 *
 * Flow: POST /api/auth/login -> store the bearer token -> GET /api/auth/me
 * (the login response itself only returns a token, not the account) -> route
 * to /admin or /dashboard depending on is_admin. A visitor who already has a
 * valid token gets bounced past this page entirely via the mount effect
 * below.
 */
export default function LoginPage() {
  const router = useRouter();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isCheckingSession, setIsCheckingSession] = useState(true);

  // Skip the login form entirely if a valid session already exists.
  useEffect(() => {
    const existingToken = getToken();
    if (!existingToken) {
      setIsCheckingSession(false);
      return;
    }
    getCurrentUser()
      .then((profile) => router.replace(profile.is_admin ? "/admin" : "/dashboard"))
      .catch(() => setIsCheckingSession(false)); // expired/invalid token -- fall through to the form
  }, [router]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const { access_token } = await login(username, password);
      setToken(access_token);
      const profile = await getCurrentUser();
      router.push(profile.is_admin ? "/admin" : "/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to reach the ITC server.");
      setIsSubmitting(false);
    }
  }

  if (isCheckingSession) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void">
        <p className="font-mono text-sm text-gray-500">Checking session…</p>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-void px-4">
      {/* Ambient grid glow, purely decorative */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(34,211,238,0.08),transparent_60%)]" />

      <div className="relative w-full max-w-sm">
        <div className="mb-8 text-center">
          <p className="font-mono text-xs uppercase tracking-[0.3em] text-accent">ITC</p>
          <h1 className="mt-2 text-xl font-semibold text-gray-100">IT Operations &amp; Systems Simulator</h1>
          <p className="mt-1 text-sm text-gray-500">Sign in to resume your ticket queue.</p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="rounded-xl border border-border bg-panel p-6 shadow-[0_0_40px_-15px_rgba(34,211,238,0.25)]"
        >
          <div className="space-y-4">
            <div>
              <label htmlFor="username" className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-400">
                Username
              </label>
              <input
                id="username"
                name="username"
                type="text"
                autoComplete="username"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full rounded-lg border border-border-soft bg-panel-raised px-3 py-2 text-sm text-gray-100 outline-none transition focus:border-accent focus:ring-1 focus:ring-accent"
                placeholder="username"
              />
            </div>

            <div>
              <label htmlFor="password" className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-400">
                Password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border border-border-soft bg-panel-raised px-3 py-2 text-sm text-gray-100 outline-none transition focus:border-accent focus:ring-1 focus:ring-accent"
                placeholder="........"
              />
            </div>
          </div>

          {error && (
            <p role="alert" className="mt-4 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={isSubmitting}
            className="mt-6 w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-void transition hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSubmitting ? "Authenticating…" : "Sign in"}
          </button>

          <p className="mt-4 text-center text-xs text-gray-600">
            No account yet?{" "}
            <Link href="/register" className="text-accent hover:underline">
              Create one
            </Link>
            .
          </p>
        </form>
      </div>
    </main>
  );
}
