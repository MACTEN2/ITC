"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getAdminSubmissions } from "@/lib/api";
import type { AdminSubmission } from "@/lib/types";
import { useSession } from "@/lib/useSession";
import AppNav from "@/components/AppNav";

const STATUS_FILTERS = ["All", "Resolved", "Open"] as const;

export default function AdminSubmissionsPage() {
  const { profile, isLoading, loadError, logout } = useSession();
  const [submissions, setSubmissions] = useState<AdminSubmission[]>([]);
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_FILTERS)[number]>("All");
  const [expandedKey, setExpandedKey] = useState<string | null>(null);

  useEffect(() => {
    if (!profile?.is_admin) return;
    getAdminSubmissions(statusFilter === "All" ? undefined : { status: statusFilter }).then(setSubmissions);
  }, [profile, statusFilter]);

  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void">
        <p className="font-mono text-sm text-gray-500">Loading submissions…</p>
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

      <main className="itc-scroll mx-auto w-full max-w-3xl flex-1 overflow-y-auto p-6">
        <div className="mb-4 flex items-center justify-between">
          <h1 className="text-lg font-semibold text-gray-100">Submission Audit Log</h1>
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
          {submissions.map((s) => {
            const key = `${s.user_id}-${s.ticket_id}`;
            const isExpanded = expandedKey === key;
            return (
              <div key={key} className="rounded-xl border border-border bg-panel">
                <button
                  onClick={() => setExpandedKey(isExpanded ? null : key)}
                  className="flex w-full items-center justify-between px-4 py-3 text-left"
                >
                  <div>
                    <p className="text-sm font-medium text-gray-100">{s.ticket_title}</p>
                    <p className="text-xs text-gray-500">
                      {s.username} · {s.department}
                    </p>
                  </div>
                  <span
                    className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${
                      s.status === "Resolved"
                        ? "border-success/30 bg-success/10 text-success"
                        : "border-border bg-panel-raised text-gray-400"
                    }`}
                  >
                    {s.status}
                  </span>
                </button>
                {isExpanded && (
                  <div className="border-t border-border-soft px-4 py-3 text-xs text-gray-400">
                    <p>
                      <span className="text-gray-500">Root cause:</span> {s.root_cause ?? "—"}
                    </p>
                    <p className="mt-1">
                      <span className="text-gray-500">Actions:</span> {s.resolution_actions.join(", ") || "—"}
                    </p>
                    <p className="mt-1">
                      <span className="text-gray-500">Notes:</span> {s.resolution_notes ?? "—"}
                    </p>
                  </div>
                )}
              </div>
            );
          })}
          {submissions.length === 0 && <p className="py-12 text-center text-sm text-gray-600">No submissions yet.</p>}
        </div>
      </main>
    </div>
  );
}
