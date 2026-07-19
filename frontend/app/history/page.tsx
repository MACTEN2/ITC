"use client";

import { useEffect, useState } from "react";
import { getTicketHistory } from "@/lib/api";
import type { TicketHistoryEntry } from "@/lib/types";
import { useSession } from "@/lib/useSession";
import AppNav from "@/components/AppNav";

const SEVERITY_DOT: Record<TicketHistoryEntry["severity"], string> = {
  Low: "bg-success",
  Incident: "bg-warning",
  Catastrophic: "bg-danger",
};

const STATUS_FILTERS = ["All", "Resolved", "Open"] as const;

export default function HistoryPage() {
  const { profile, isLoading, loadError, logout } = useSession();
  const [entries, setEntries] = useState<TicketHistoryEntry[]>([]);
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_FILTERS)[number]>("All");
  const [isFetchingHistory, setIsFetchingHistory] = useState(false);

  useEffect(() => {
    if (!profile) return;
    setIsFetchingHistory(true);
    getTicketHistory(statusFilter === "All" ? undefined : { status: statusFilter })
      .then(setEntries)
      .finally(() => setIsFetchingHistory(false));
  }, [profile, statusFilter]);

  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void">
        <p className="font-mono text-sm text-gray-500">Loading history…</p>
      </main>
    );
  }

  if (loadError || !profile) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void px-4">
        <p className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
          {loadError ?? "Could not load your history."}
        </p>
      </main>
    );
  }

  return (
    <div className="flex h-screen flex-col bg-void">
      <AppNav profile={profile} onLogout={logout} />

      <main className="itc-scroll mx-auto w-full max-w-3xl flex-1 overflow-y-auto p-6">
        <div className="mb-4 flex items-center justify-between">
          <h1 className="text-lg font-semibold text-gray-100">Ticket History</h1>
          <div className="flex gap-1">
            {STATUS_FILTERS.map((status) => (
              <button
                key={status}
                onClick={() => setStatusFilter(status)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                  statusFilter === status ? "bg-accent-dim/40 text-accent" : "text-gray-400 hover:bg-panel-raised hover:text-gray-200"
                }`}
              >
                {status}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          {entries.map((entry) => (
            <div
              key={entry.ticket_id}
              className="flex items-center justify-between rounded-xl border border-border bg-panel px-4 py-3"
            >
              <div className="flex items-center gap-3">
                <span className={`h-2 w-2 shrink-0 rounded-full ${SEVERITY_DOT[entry.severity]}`} />
                <div>
                  <p className="text-sm font-medium text-gray-100">{entry.ticket_title}</p>
                  <p className="text-xs text-gray-500">
                    {entry.department} ·{" "}
                    {new Date(entry.resolved_at ?? entry.unlocked_at).toLocaleString()}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                {entry.status === "Resolved" && entry.reward_amount ? (
                  <span className="font-mono text-xs text-accent">
                    +{entry.reward_amount} {entry.reward_field === "infra_points" ? "infra pts" : "XP"}
                  </span>
                ) : null}
                <span
                  className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${
                    entry.status === "Resolved"
                      ? "border-success/30 bg-success/10 text-success"
                      : "border-border bg-panel-raised text-gray-400"
                  }`}
                >
                  {entry.status}
                </span>
              </div>
            </div>
          ))}
          {!isFetchingHistory && entries.length === 0 && (
            <p className="py-12 text-center text-sm text-gray-600">No ticket activity yet.</p>
          )}
        </div>
      </main>
    </div>
  );
}
