"use client";

import { use } from "react";
import { getPublicUserProfile } from "@/lib/api";
import type { PublicUserProfile } from "@/lib/types";
import { useSession } from "@/lib/useSession";
import AppNav from "@/components/AppNav";

export default function PublicProfilePage({ params }: { params: Promise<{ username: string }> }) {
  const { username } = use(params);
  const { profile, extra: publicProfile, isLoading, loadError, logout } = useSession<PublicUserProfile>(() =>
    getPublicUserProfile(username),
  );

  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void">
        <p className="font-mono text-sm text-gray-500">Loading profile…</p>
      </main>
    );
  }

  if (loadError || !profile || !publicProfile) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void px-4">
        <p className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
          {loadError ?? `Could not find user '${username}'.`}
        </p>
      </main>
    );
  }

  const totalXp = publicProfile.networking_xp + publicProfile.automation_xp + publicProfile.database_xp;
  const earnedBadges = publicProfile.badges.filter((b) => b.earned);

  return (
    <div className="flex h-screen flex-col bg-void">
      <AppNav profile={profile} onLogout={logout} />

      <main className="itc-scroll mx-auto w-full max-w-2xl flex-1 overflow-y-auto p-6">
        <div className="rounded-xl border border-border bg-panel p-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-lg font-semibold text-gray-100">
                {publicProfile.username}
                {publicProfile.is_admin && <span className="ml-2 text-xs text-warning">admin</span>}
              </h1>
              <p className="text-sm text-gray-500">{publicProfile.current_role}</p>
            </div>
            <p className="font-mono text-sm text-accent">
              {totalXp} XP{publicProfile.infra_points > 0 && ` · ${publicProfile.infra_points} infra pts`}
            </p>
          </div>
          <dl className="mt-4 grid grid-cols-3 gap-4 font-mono text-xs">
            <div>
              <dt className="text-gray-500">NETWORKING</dt>
              <dd className="mt-0.5 text-gray-200">{publicProfile.networking_xp} XP</dd>
            </div>
            <div>
              <dt className="text-gray-500">AUTOMATION</dt>
              <dd className="mt-0.5 text-gray-200">{publicProfile.automation_xp} XP</dd>
            </div>
            <div>
              <dt className="text-gray-500">DATABASE</dt>
              <dd className="mt-0.5 text-gray-200">{publicProfile.database_xp} XP</dd>
            </div>
          </dl>
          <p className="mt-4 text-xs text-gray-500">
            Member since {new Date(publicProfile.created_at).toLocaleDateString()}
          </p>
        </div>

        <div className="mt-6 rounded-xl border border-border bg-panel p-6">
          <h2 className="text-sm font-semibold text-gray-100">
            Badges <span className="font-mono text-xs text-gray-500">({earnedBadges.length}/{publicProfile.badges.length})</span>
          </h2>
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
            {publicProfile.badges.map((badge) => (
              <div
                key={badge.id}
                className={`rounded-xl border p-3 text-center ${
                  badge.earned ? "border-accent/40 bg-accent-dim/10" : "border-border bg-panel-raised opacity-50"
                }`}
              >
                <p className="text-xl">{badge.icon}</p>
                <p className="mt-1 text-xs font-medium text-gray-200">{badge.name}</p>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
