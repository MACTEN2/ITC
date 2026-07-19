"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getAnalyticsSummary, getDepartmentStats, getLeaderboard } from "@/lib/api";
import type { AnalyticsSummary, DepartmentStats, LeaderboardEntry } from "@/lib/types";
import { useSession } from "@/lib/useSession";
import AppNav from "@/components/AppNav";

function StatTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-border bg-panel p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</p>
      <p className="mt-1.5 font-mono text-xl font-semibold text-gray-100">{value}</p>
    </div>
  );
}

/** A single-series horizontal bar comparison -- one hue (accent) throughout,
 * since there's only one measure (resolution rate) per category, so no
 * categorical legend is needed (the row label names the category). Each row
 * also prints the raw resolved/attempted counts directly, so the numbers
 * are readable without depending on hover. */
function DepartmentBar({ stat }: { stat: DepartmentStats }) {
  const percent = Math.round(stat.resolution_rate * 100);
  return (
    <div title={`${stat.resolved_count} of ${stat.total_attempts} attempts resolved`}>
      <div className="mb-1 flex items-baseline justify-between text-xs">
        <span className="font-medium text-gray-300">{stat.department}</span>
        <span className="font-mono text-gray-500">
          {percent}% · {stat.resolved_count}/{stat.total_attempts} attempts · {stat.unique_learners_engaged} learners
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-panel-raised">
        <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}

export default function AnalyticsPage() {
  const { profile, isLoading, loadError, logout } = useSession();
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [departments, setDepartments] = useState<DepartmentStats[]>([]);
  const [topFive, setTopFive] = useState<LeaderboardEntry[]>([]);

  useEffect(() => {
    if (!profile?.is_admin) return;
    getAnalyticsSummary().then(setSummary);
    getDepartmentStats().then(setDepartments);
    getLeaderboard("total", 5).then((res) => setTopFive(res.entries));
  }, [profile]);

  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void">
        <p className="font-mono text-sm text-gray-500">Loading analytics…</p>
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

      <main className="itc-scroll mx-auto w-full max-w-4xl flex-1 overflow-y-auto p-6">
        <h1 className="text-lg font-semibold text-gray-100">Operations Analytics</h1>

        {summary && (
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            <StatTile label="Total Users" value={summary.total_users} />
            <StatTile label="Tickets Resolved" value={summary.total_tickets_resolved} />
            <StatTile label="Avg Resolution Rate" value={`${Math.round(summary.average_resolution_rate * 100)}%`} />
            <StatTile label="Most Active Dept" value={summary.most_active_department ?? "—"} />
            <StatTile label="Badges Unlocked" value={summary.total_badges_unlocked} />
          </div>
        )}

        <section className="mt-6 rounded-xl border border-border bg-panel p-5">
          <h2 className="text-sm font-semibold text-gray-100">Resolution Rate by Department</h2>
          <div className="mt-4 space-y-4">
            {departments.map((stat) => (
              <DepartmentBar key={stat.department} stat={stat} />
            ))}
            {departments.length === 0 && <p className="text-sm text-gray-600">No department data yet.</p>}
          </div>
        </section>

        <section className="mt-6 rounded-xl border border-border bg-panel p-5">
          <h2 className="text-sm font-semibold text-gray-100">Top 5 — Total XP</h2>
          <div className="mt-3 space-y-1.5">
            {topFive.map((entry) => (
              <div key={entry.user_id} className="flex items-center justify-between rounded-lg px-2 py-1.5 text-sm">
                <span className="text-gray-300">
                  #{entry.rank} {entry.username}
                </span>
                <span className="font-mono text-accent">{entry.value}</span>
              </div>
            ))}
            {topFive.length === 0 && <p className="text-sm text-gray-600">No ranked users yet.</p>}
          </div>
        </section>
      </main>
    </div>
  );
}
