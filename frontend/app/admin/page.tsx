"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { getAdminTickets } from "@/lib/api";
import type { GradingResult, Ticket } from "@/lib/types";
import { useSession } from "@/lib/useSession";
import AppNav from "@/components/AppNav";
import TicketResolutionWorkspace from "@/components/TicketResolutionWorkspace";

// Purely decorative simulated telemetry -- there is no backend endpoint for
// live server status, so this is a canned pool of lines cycled on a timer to
// sell the "operational terminal" feel. Do not mistake this for real
// monitoring data.
const SIMULATED_LOG_POOL = [
  "[monitor] disk usage on db-primary-02 at 91% and rising",
  "[auth] 3 failed login attempts from 203.0.113.10 in the last 5m",
  "[cron] nightly backup job completed in 4m12s",
  "[net] latency spike detected on edge-router-04 (312ms avg)",
  "[compliance] contractor access review due in 2 days",
  "[fs] /var/log partition approaching retention limit on app-03",
  "[alert] TLS certificate for api.internal expires in 9 days",
  "[queue] 2 tickets unresolved for over 24h in the SysAdmin queue",
  "[auth] service account token rotated for ci-deploy-bot",
  "[net] edge-router-04 recovered, latency nominal",
];

const MAX_VISIBLE_LOG_LINES = 30;

/**
 * The SysAdmin Infrastructure Panel -- gated behind `is_admin`.
 *
 * State management:
 *   - `profile`/`isLoading`/`loadError`/`logout`: from `useSession`.
 *     `profile.is_admin` is the client-side gate that decides whether this
 *     component renders the dashboard or the "Access Restricted" panel.
 *     This is a UX convenience only -- the real authorization boundary is
 *     server-side (`require_admin` in app/routes/admin.py, returning 403),
 *     which this page's own API calls remain subject to regardless of what
 *     this flag says.
 *   - `adminTickets` / `selectedTicket`: same catalog + workspace pattern as
 *     the learner dashboard, pointed at the admin-tier endpoints instead.
 *   - `terminalLines`: simulated status feed, appended to on an interval.
 */
export default function AdminPage() {
  const { profile, setProfile, isLoading, loadError, logout } = useSession();

  const [adminTickets, setAdminTickets] = useState<Ticket[]>([]);
  const [selectedTicket, setSelectedTicket] = useState<Ticket | null>(null);
  const [unlockedBanner, setUnlockedBanner] = useState<string | null>(null);
  const [terminalLines, setTerminalLines] = useState<string[]>([]);

  const terminalRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (profile?.is_admin) {
      getAdminTickets().then(setAdminTickets);
    }
  }, [profile]);

  // Simulated status feed -- see SIMULATED_LOG_POOL comment above.
  useEffect(() => {
    let cursor = 0;
    const interval = setInterval(() => {
      const timestamp = new Date().toLocaleTimeString();
      const line = `${timestamp}  ${SIMULATED_LOG_POOL[cursor % SIMULATED_LOG_POOL.length]}`;
      cursor += 1;
      setTerminalLines((prev) => [...prev.slice(-(MAX_VISIBLE_LOG_LINES - 1)), line]);
    }, 2500);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    terminalRef.current?.scrollTo({ top: terminalRef.current.scrollHeight });
  }, [terminalLines]);

  function handleResolved(result: GradingResult) {
    setProfile((prev) => (prev ? { ...prev, ...result.user } : prev));
    if (result.badges_unlocked.length > 0) {
      setUnlockedBanner(`🏅 Badge unlocked: ${result.badges_unlocked.map((b) => b.name).join(", ")}`);
    }
  }

  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void">
        <p className="font-mono text-sm text-gray-500">Verifying clearance…</p>
      </main>
    );
  }

  if (loadError) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void px-4">
        <p className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">{loadError}</p>
      </main>
    );
  }

  // --- Access gate: block cleanly for any non-admin profile. ---
  if (!profile?.is_admin) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void px-4">
        <div className="max-w-md rounded-xl border border-warning/30 bg-warning/5 p-8 text-center">
          <p className="text-3xl">🔒</p>
          <h1 className="mt-4 text-lg font-semibold text-gray-100">Access Restricted</h1>
          <p className="mt-2 text-sm text-gray-400">
            This area requires SysAdmin-tier clearance. Your account (
            <span className="font-mono text-gray-300">{profile?.current_role ?? "unknown role"}</span>) does not have
            the <code className="font-mono text-warning">is_admin</code> flag set.
          </p>
          <Link
            href="/dashboard"
            className="mt-6 inline-block rounded-lg bg-panel-raised px-4 py-2 text-sm font-medium text-gray-200 transition hover:bg-border"
          >
            Return to Dashboard
          </Link>
        </div>
      </main>
    );
  }

  return (
    <div className="flex h-screen flex-col bg-void">
      <AppNav profile={profile} onLogout={logout} />

      {/* Header */}
      <header className="flex items-center justify-between border-b border-border bg-panel px-6 py-4">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.3em] text-warning">ITC · Admin</p>
          <h1 className="mt-1 text-lg font-semibold text-gray-100">SysAdmin Infrastructure Panel</h1>
        </div>
        <p className="font-mono text-sm text-gray-400">
          {profile.infra_points} <span className="text-gray-600">infra points</span>
        </p>
      </header>

      <div className="grid flex-1 grid-cols-1 gap-4 overflow-hidden p-6 lg:grid-cols-3">
        {/* Ticket queue / workspace */}
        <section className="itc-scroll overflow-y-auto lg:col-span-2">
          {selectedTicket ? (
            <div className="h-full">
              {unlockedBanner && (
                <p className="mb-3 rounded-lg border border-accent/30 bg-accent-dim/10 px-3 py-2 text-sm text-accent">
                  {unlockedBanner}
                </p>
              )}
              <TicketResolutionWorkspace
                key={selectedTicket.id}
                ticket={selectedTicket}
                mode="admin"
                onClose={() => {
                  setSelectedTicket(null);
                  setUnlockedBanner(null);
                }}
                onResolved={handleResolved}
              />
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {adminTickets.map((ticket) => (
                <button
                  key={ticket.id}
                  onClick={() => setSelectedTicket(ticket)}
                  className="flex flex-col items-start rounded-xl border border-border bg-panel p-4 text-left transition hover:border-warning/50 hover:bg-panel-raised"
                >
                  <span className="rounded-full border border-warning/30 bg-warning/10 px-2.5 py-0.5 text-xs font-medium text-warning">
                    {ticket.severity}
                  </span>
                  <h3 className="mt-2 text-sm font-semibold text-gray-100">{ticket.title}</h3>
                  <p className="mt-1 text-xs text-gray-500">{ticket.department}</p>
                  <p className="mt-3 line-clamp-3 text-xs text-gray-400">{ticket.problem_description}</p>
                </button>
              ))}
              {adminTickets.length === 0 && (
                <p className="col-span-full py-12 text-center text-sm text-gray-600">No admin tickets queued.</p>
              )}
            </div>
          )}
        </section>

        {/* Operational terminal */}
        <section className="flex flex-col overflow-hidden rounded-xl border border-border bg-panel">
          <div className="border-b border-border px-4 py-2.5">
            <p className="font-mono text-xs uppercase tracking-wide text-gray-500">Operational Feed (simulated)</p>
          </div>
          <div ref={terminalRef} className="itc-scroll flex-1 overflow-y-auto bg-void p-4 font-mono text-xs leading-relaxed">
            {terminalLines.map((line, idx) => (
              <p key={idx} className="text-success/80">
                {line}
              </p>
            ))}
            <span className="inline-block h-3 w-1.5 animate-pulse bg-success/70 align-middle" />
          </div>
        </section>
      </div>
    </div>
  );
}
