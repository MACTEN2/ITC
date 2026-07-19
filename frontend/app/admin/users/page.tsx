"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getAdminUsers } from "@/lib/api";
import type { AdminUser } from "@/lib/types";
import { useSession } from "@/lib/useSession";
import AppNav from "@/components/AppNav";

export default function AdminUsersPage() {
  const { profile, isLoading, loadError, logout } = useSession();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (!profile?.is_admin) return;
    const handle = setTimeout(() => {
      getAdminUsers({ q: search || undefined }).then(setUsers);
    }, 250);
    return () => clearTimeout(handle);
  }, [profile, search]);

  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void">
        <p className="font-mono text-sm text-gray-500">Loading users…</p>
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
        <div className="mb-4 flex items-center justify-between">
          <h1 className="text-lg font-semibold text-gray-100">User Management</h1>
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search username or email…"
            className="w-64 rounded-lg border border-border-soft bg-panel-raised px-3 py-2 text-sm text-gray-200 outline-none"
          />
        </div>

        <div className="itc-scroll overflow-x-auto rounded-xl border border-border bg-panel">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-border text-xs uppercase tracking-wide text-gray-500">
                <th className="px-4 py-3 font-medium">User</th>
                <th className="px-4 py-3 font-medium">Role</th>
                <th className="px-4 py-3 font-medium">Total XP</th>
                <th className="px-4 py-3 font-medium">Badges</th>
                <th className="px-4 py-3 font-medium">Resolved</th>
                <th className="px-4 py-3 font-medium">Joined</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id} className="border-b border-border-soft last:border-0">
                  <td className="px-4 py-3">
                    <Link href={`/users/${user.username}`} className="text-gray-200 hover:text-accent">
                      {user.username}
                    </Link>
                    {user.is_admin && <span className="ml-2 text-xs text-warning">admin</span>}
                    <p className="text-xs text-gray-500">{user.email}</p>
                  </td>
                  <td className="px-4 py-3 text-gray-400">{user.current_role}</td>
                  <td className="px-4 py-3 font-mono text-gray-300">
                    {user.networking_xp + user.automation_xp + user.database_xp}
                  </td>
                  <td className="px-4 py-3 font-mono text-gray-300">{user.badges_earned}</td>
                  <td className="px-4 py-3 font-mono text-gray-300">{user.resolved_ticket_count}</td>
                  <td className="px-4 py-3 text-gray-500">{new Date(user.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
              {users.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-gray-600">
                    No users found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </main>
    </div>
  );
}
