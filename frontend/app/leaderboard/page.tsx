"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getLeaderboard } from "@/lib/api";
import type { LeaderboardResponse, LeaderboardTrack } from "@/lib/types";
import { useSession } from "@/lib/useSession";
import AppNav from "@/components/AppNav";

const TRACKS: { value: LeaderboardTrack; label: string }[] = [
  { value: "total", label: "Total XP" },
  { value: "networking", label: "Networking" },
  { value: "automation", label: "Automation" },
  { value: "database", label: "Database" },
  { value: "infra_points", label: "Infra Points" },
];

export default function LeaderboardPage() {
  const { profile, isLoading, loadError, logout } = useSession();
  const [track, setTrack] = useState<LeaderboardTrack>("total");
  const [data, setData] = useState<LeaderboardResponse | null>(null);

  useEffect(() => {
    if (!profile) return;
    getLeaderboard(track).then(setData);
  }, [profile, track]);

  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void">
        <p className="font-mono text-sm text-gray-500">Loading leaderboard…</p>
      </main>
    );
  }

  if (loadError || !profile) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void px-4">
        <p className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
          {loadError ?? "Could not load the leaderboard."}
        </p>
      </main>
    );
  }

  return (
    <div className="flex h-screen flex-col bg-void">
      <AppNav profile={profile} onLogout={logout} />

      <main className="itc-scroll mx-auto w-full max-w-2xl flex-1 overflow-y-auto p-6">
        <div className="mb-4 flex items-center justify-between">
          <h1 className="text-lg font-semibold text-gray-100">Leaderboard</h1>
          {data?.your_rank && (
            <p className="font-mono text-xs text-gray-500">
              Your rank: <span className="text-accent">#{data.your_rank.rank}</span> ({data.your_rank.value})
            </p>
          )}
        </div>

        <div className="mb-4 flex flex-wrap gap-1">
          {TRACKS.map((t) => (
            <button
              key={t.value}
              onClick={() => setTrack(t.value)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                track === t.value ? "bg-accent-dim/40 text-accent" : "text-gray-400 hover:bg-panel-raised hover:text-gray-200"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="space-y-1.5">
          {data?.entries.map((entry) => (
            <div
              key={entry.user_id}
              className={`flex items-center justify-between rounded-xl border px-4 py-3 ${
                entry.user_id === profile.id ? "border-accent/50 bg-accent-dim/10" : "border-border bg-panel"
              }`}
            >
              <div className="flex items-center gap-3">
                <span className="w-6 font-mono text-sm text-gray-500">#{entry.rank}</span>
                <div>
                  <Link href={`/users/${entry.username}`} className="text-sm font-medium text-gray-100 hover:text-accent">
                    {entry.username}
                    {entry.is_admin && <span className="ml-1.5 text-xs text-warning">admin</span>}
                  </Link>
                  <p className="text-xs text-gray-500">{entry.current_role}</p>
                </div>
              </div>
              <span className="font-mono text-sm text-accent">{entry.value}</span>
            </div>
          ))}
          {data && data.entries.length === 0 && (
            <p className="py-12 text-center text-sm text-gray-600">No ranked users yet.</p>
          )}
        </div>
      </main>
    </div>
  );
}
