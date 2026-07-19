"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { getAchievements, getNotifications } from "@/lib/api";
import type { UserProfile } from "@/lib/types";
import CommandPalette from "@/components/CommandPalette";

interface AppNavProps {
  profile: UserProfile;
  onLogout: () => void;
}

const LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/leaderboard", label: "Leaderboard" },
  { href: "/history", label: "History" },
  { href: "/achievements", label: "Achievements" },
] as const;

/**
 * Shared top bar for every authenticated page. Fetches its own unread
 * notification count and earned-badge count on mount rather than pulling
 * from any shared/global state -- there is no session context in this app
 * (see lib/useSession.ts), so every page independently owns what it needs,
 * and this is a cheap couple of extra GETs per navigation in exchange for
 * not introducing a global store.
 */
export default function AppNav({ profile, onLogout }: AppNavProps) {
  const pathname = usePathname();
  const [unreadCount, setUnreadCount] = useState(0);
  const [badgeCount, setBadgeCount] = useState<{ earned: number; total: number } | null>(null);
  const [isPaletteOpen, setIsPaletteOpen] = useState(false);

  useEffect(() => {
    getNotifications({ unread_only: true })
      .then((notifications) => setUnreadCount(notifications.length))
      .catch(() => undefined);
    getAchievements()
      .then((badges) => setBadgeCount({ earned: badges.filter((b) => b.earned).length, total: badges.length }))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setIsPaletteOpen(true);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <nav className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-panel px-4">
      <div className="flex items-center gap-6">
        <span className="font-mono text-xs font-semibold uppercase tracking-[0.3em] text-accent">ITC</span>
        <button
          onClick={() => setIsPaletteOpen(true)}
          className="rounded-lg border border-border-soft bg-panel-raised px-3 py-1.5 text-xs text-gray-500 transition hover:text-gray-300"
        >
          Search… <span className="font-mono">⌘K</span>
        </button>
        <div className="flex items-center gap-1">
          {LINKS.map((link) => {
            const isActive = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`rounded-lg px-3 py-1.5 text-sm transition ${
                  isActive ? "bg-accent-dim/40 text-accent" : "text-gray-400 hover:bg-panel-raised hover:text-gray-200"
                }`}
              >
                {link.label}
                {link.href === "/achievements" && badgeCount && (
                  <span className="ml-1.5 font-mono text-xs text-gray-500">
                    {badgeCount.earned}/{badgeCount.total}
                  </span>
                )}
              </Link>
            );
          })}
        </div>
      </div>

      <div className="flex items-center gap-1">
        {profile.is_admin && (
          <>
            <Link
              href="/admin"
              className={`rounded-lg px-3 py-1.5 text-sm transition ${
                pathname === "/admin" ? "bg-warning/10 text-warning" : "text-gray-400 hover:bg-panel-raised hover:text-gray-200"
              }`}
            >
              Admin Panel
            </Link>
            <Link
              href="/analytics"
              className={`rounded-lg px-3 py-1.5 text-sm transition ${
                pathname === "/analytics" ? "bg-warning/10 text-warning" : "text-gray-400 hover:bg-panel-raised hover:text-gray-200"
              }`}
            >
              Analytics
            </Link>
            <Link
              href="/admin/users"
              className={`rounded-lg px-3 py-1.5 text-sm transition ${
                pathname === "/admin/users" ? "bg-warning/10 text-warning" : "text-gray-400 hover:bg-panel-raised hover:text-gray-200"
              }`}
            >
              Users
            </Link>
            <Link
              href="/admin/submissions"
              className={`rounded-lg px-3 py-1.5 text-sm transition ${
                pathname === "/admin/submissions" ? "bg-warning/10 text-warning" : "text-gray-400 hover:bg-panel-raised hover:text-gray-200"
              }`}
            >
              Audit Log
            </Link>
          </>
        )}
        <Link
          href="/notifications"
          aria-label="Notifications"
          className={`relative rounded-lg px-3 py-1.5 text-sm transition ${
            pathname === "/notifications" ? "bg-accent-dim/40 text-accent" : "text-gray-400 hover:bg-panel-raised hover:text-gray-200"
          }`}
        >
          🔔
          {unreadCount > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 font-mono text-[10px] font-semibold text-void">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          )}
        </Link>
        <Link
          href="/profile"
          className={`rounded-lg px-3 py-1.5 text-sm transition ${
            pathname === "/profile" ? "bg-accent-dim/40 text-accent" : "text-gray-400 hover:bg-panel-raised hover:text-gray-200"
          }`}
        >
          {profile.username}
        </Link>
        <Link
          href="/settings"
          aria-label="Settings"
          className={`rounded-lg px-3 py-1.5 text-sm transition ${
            pathname === "/settings" ? "bg-accent-dim/40 text-accent" : "text-gray-400 hover:bg-panel-raised hover:text-gray-200"
          }`}
        >
          ⚙️
        </Link>
        <button
          onClick={onLogout}
          className="rounded-lg px-3 py-1.5 text-sm text-gray-500 transition hover:bg-panel-raised hover:text-gray-200"
        >
          Sign out
        </button>
      </div>

      <CommandPalette profile={profile} isOpen={isPaletteOpen} onClose={() => setIsPaletteOpen(false)} />
    </nav>
  );
}
