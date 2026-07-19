"use client";

import { getAchievements } from "@/lib/api";
import { useSession } from "@/lib/useSession";
import AppNav from "@/components/AppNav";
import type { AchievementBadge } from "@/lib/types";

export default function AchievementsPage() {
  const { profile, extra: badges, isLoading, loadError, logout } = useSession<AchievementBadge[]>(getAchievements);

  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void">
        <p className="font-mono text-sm text-gray-500">Loading achievements…</p>
      </main>
    );
  }

  if (loadError || !profile) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void px-4">
        <p className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
          {loadError ?? "Could not load achievements."}
        </p>
      </main>
    );
  }

  const earnedCount = badges?.filter((b) => b.earned).length ?? 0;

  return (
    <div className="flex h-screen flex-col bg-void">
      <AppNav profile={profile} onLogout={logout} />

      <main className="itc-scroll mx-auto w-full max-w-3xl flex-1 overflow-y-auto p-6">
        <div className="mb-4 flex items-center justify-between">
          <h1 className="text-lg font-semibold text-gray-100">Achievements</h1>
          <p className="font-mono text-xs text-gray-500">
            {earnedCount}/{badges?.length ?? 0} unlocked
          </p>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
          {badges?.map((badge) => (
            <div
              key={badge.id}
              className={`rounded-xl border p-4 transition ${
                badge.earned ? "border-accent/40 bg-accent-dim/10" : "border-border bg-panel opacity-60"
              }`}
            >
              <p className="text-2xl">{badge.icon}</p>
              <h3 className="mt-2 text-sm font-semibold text-gray-100">{badge.name}</h3>
              <p className="mt-1 text-xs text-gray-500">{badge.description}</p>
              {badge.earned && badge.earned_at && (
                <p className="mt-2 font-mono text-xs text-accent">
                  Earned {new Date(badge.earned_at).toLocaleDateString()}
                </p>
              )}
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
