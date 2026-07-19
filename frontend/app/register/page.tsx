"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError, getCurrentUser, login, register, setToken } from "@/lib/api";

/**
 * Account provisioning -- create a Help Desk Tier 1 profile, then sign the
 * new account straight in.
 *
 * State management:
 *   - `username` / `email` / `password` / `confirmPassword`: controlled
 *     form inputs. `confirmPassword` is a client-side-only nicety -- the
 *     backend never sees it.
 *   - `isSubmitting`: disables the form and swaps the button label while the
 *     register -> login -> profile-fetch round trip is in flight.
 *   - `error`: last request failure, surfaced inline; cleared on every new
 *     submit attempt so a stale error doesn't linger after a retry.
 *
 * Flow: POST /api/auth/register -> (registration only returns the new
 * profile, not a session) -> POST /api/auth/login -> store the bearer token
 * -> GET /api/auth/me -> route to /admin or /dashboard depending on
 * is_admin, exactly like the login page's own post-auth redirect.
 */
export default function RegisterPage() {
  const router = useRouter();

  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setIsSubmitting(true);
    try {
      await register(username, email, password);
      const { access_token } = await login(username, password);
      setToken(access_token);
      const profile = await getCurrentUser();
      router.push(profile.is_admin ? "/admin" : "/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to reach the ITC server.");
      setIsSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-void px-4">
      {/* Ambient grid glow, purely decorative */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(34,211,238,0.08),transparent_60%)]" />

      <div className="relative w-full max-w-sm">
        <div className="mb-8 text-center">
          <p className="font-mono text-xs uppercase tracking-[0.3em] text-accent">ITC</p>
          <h1 className="mt-2 text-xl font-semibold text-gray-100">Create your account</h1>
          <p className="mt-1 text-sm text-gray-500">Provision a new Help Desk Tier 1 profile.</p>
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
                minLength={3}
                maxLength={64}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full rounded-lg border border-border-soft bg-panel-raised px-3 py-2 text-sm text-gray-100 outline-none transition focus:border-accent focus:ring-1 focus:ring-accent"
                placeholder="jsmith"
              />
            </div>

            <div>
              <label htmlFor="email" className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-400">
                Email
              </label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg border border-border-soft bg-panel-raised px-3 py-2 text-sm text-gray-100 outline-none transition focus:border-accent focus:ring-1 focus:ring-accent"
                placeholder="jsmith@company.com"
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
                autoComplete="new-password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border border-border-soft bg-panel-raised px-3 py-2 text-sm text-gray-100 outline-none transition focus:border-accent focus:ring-1 focus:ring-accent"
                placeholder="Minimum 8 characters"
              />
            </div>

            <div>
              <label
                htmlFor="confirmPassword"
                className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-gray-400"
              >
                Confirm password
              </label>
              <input
                id="confirmPassword"
                name="confirmPassword"
                type="password"
                autoComplete="new-password"
                required
                minLength={8}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full rounded-lg border border-border-soft bg-panel-raised px-3 py-2 text-sm text-gray-100 outline-none transition focus:border-accent focus:ring-1 focus:ring-accent"
                placeholder="••••••••"
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
            {isSubmitting ? "Provisioning account…" : "Create account"}
          </button>

          <p className="mt-4 text-center text-xs text-gray-600">
            Already have an account?{" "}
            <Link href="/login" className="text-accent hover:underline">
              Sign in
            </Link>
            .
          </p>
        </form>
      </div>
    </main>
  );
}
