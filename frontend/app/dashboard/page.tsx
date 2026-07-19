"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { getAchievements, getLeaderboard, getNotifications, getTickets, getTicketHistory } from "@/lib/api";
import type {
  AchievementBadge,
  GradingResult,
  LeaderboardEntry,
  Notification,
  RankInfo,
  Severity,
  Ticket,
  TicketHistoryEntry,
} from "@/lib/types";
import { getDisplayPreferences, type Density } from "@/lib/preferences";
import { useSession } from "@/lib/useSession";
import AppNav from "@/components/AppNav";
import TicketResolutionWorkspace from "@/components/TicketResolutionWorkspace";

// Sidebar categories map onto the `department` field tickets are seeded
// with on the backend (see app/tickets_db.py) -- "All" is a synthetic entry
// that skips filtering entirely.
const NAV_SECTIONS = [
  { label: "All Tickets", department: null },
  { label: "Help Desk Tickets", department: "Help Desk" },
  { label: "Network Support", department: "Network Operations" },
  { label: "Database Administration", department: "Database Administration" },
] as const;

const SEVERITY_FILTERS: { label: string; value: Severity | null }[] = [
  { label: "All", value: null },
  { label: "Low", value: "Low" },
  { label: "Incident", value: "Incident" },
  { label: "Catastrophic", value: "Catastrophic" },
];

const SEVERITY_DOT: Record<Ticket["severity"], string> = {
  Low: "bg-success",
  Incident: "bg-warning",
  Catastrophic: "bg-danger",
};

/**
 * The Student Command Center.
 *
 * State management:
 *   - `profile`/`isLoading`/`loadError`/`logout`: from `useSession`, the
 *     shared auth-gate hook every protected page uses.
 *   - `tickets`: refetched from the backend (not filtered client-side)
 *     whenever `activeDepartment`, `severityFilter`, or the debounced
 *     `searchTerm` changes -- this actually exercises the search/filter
 *     query params added to `GET /api/tickets`.
 *   - `selectedTicket`: which ticket's resolution workspace is open, if any --
 *     when set, it replaces the central feed entirely (see render below).
 *   - `resolvedIds`: tickets resolved this session, tracked client-side so
 *     the feed can show a checkmark without re-fetching the whole catalog.
 *   - `recentActivity`/`badgeSummary`/`rank`/`topThree`/`notificationsPreview`:
 *     lightweight sidebar widgets fetched once profile is known, each from
 *     its own new endpoint.
 *   - `unlockedBanner`: badges surfaced by a submission response, shown as a
 *     transient banner in the workspace pane.
 */
export default function DashboardPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center bg-void">
          <p className="font-mono text-sm text-gray-500">Loading command center…</p>
        </main>
      }
    >
      <DashboardContent />
    </Suspense>
  );
}

function DashboardContent() {
  const { profile, setProfile, isLoading, loadError, logout } = useSession();
  const searchParams = useSearchParams();
  const ticketParam = searchParams.get("ticket");

  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [isFetchingTickets, setIsFetchingTickets] = useState(false);
  const [activeDepartment, setActiveDepartment] = useState<string | null>(
    () => getDisplayPreferences().defaultDepartment,
  );
  const [density] = useState<Density>(() => getDisplayPreferences().density);
  const [severityFilter, setSeverityFilter] = useState<Severity | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [selectedTicket, setSelectedTicket] = useState<Ticket | null>(null);
  const [resolvedIds, setResolvedIds] = useState<Set<number>>(new Set());
  const [unlockedBanner, setUnlockedBanner] = useState<string | null>(null);

  const [recentActivity, setRecentActivity] = useState<TicketHistoryEntry[]>([]);
  const [badgeSummary, setBadgeSummary] = useState<AchievementBadge[] | null>(null);
  const [rank, setRank] = useState<RankInfo | null>(null);
  const [topThree, setTopThree] = useState<LeaderboardEntry[]>([]);
  const [notificationsPreview, setNotificationsPreview] = useState<Notification[]>([]);

  // Debounce the free-text search box so every keystroke doesn't trigger a request.
  useEffect(() => {
    const handle = setTimeout(() => setDebouncedSearch(searchInput.trim()), 300);
    return () => clearTimeout(handle);
  }, [searchInput]);

  // Re-fetch the ticket catalog whenever a filter changes, once we have a session.
  // A `?ticket=` deep link (from the command palette) skips department/severity
  // filtering for this one fetch, so the target ticket is guaranteed to be in
  // the loaded set even if it doesn't match the current filter selection.
  useEffect(() => {
    if (!profile) return;
    setIsFetchingTickets(true);
    getTickets({
      department: ticketParam ? undefined : activeDepartment ?? undefined,
      severity: ticketParam ? undefined : severityFilter ?? undefined,
      q: ticketParam ? undefined : debouncedSearch || undefined,
    })
      .then(setTickets)
      .finally(() => setIsFetchingTickets(false));
  }, [profile, activeDepartment, severityFilter, debouncedSearch, ticketParam]);

  // Sidebar widgets: recent activity, badge summary, leaderboard rank/top 3,
  // notifications preview -- each independent of the filtered ticket catalog
  // above, fetched once per session load.
  useEffect(() => {
    if (!profile) return;
    getTicketHistory().then((entries) => setRecentActivity(entries.slice(0, 5)));
    getAchievements().then(setBadgeSummary);
    getLeaderboard("total").then((res) => {
      setRank(res.your_rank);
      setTopThree(res.entries.slice(0, 3));
    });
    getNotifications({ unread_only: true, limit: 3 }).then(setNotificationsPreview);
  }, [profile]);

  const visibleTickets = useMemo(() => tickets, [tickets]);

  // Deep-link support: the command palette's ticket search results navigate to
  // /dashboard?ticket=<id>. Once the catalog is loaded, open that ticket directly.
  useEffect(() => {
    if (!ticketParam || selectedTicket) return;
    const match = tickets.find((t) => t.id === Number(ticketParam));
    if (match) setSelectedTicket(match);
  }, [ticketParam, tickets, selectedTicket]);

  function handleResolved(ticketId: number, result: GradingResult) {
    if (result.passed) {
      setResolvedIds((prev) => new Set(prev).add(ticketId));
      getTicketHistory().then((entries) => setRecentActivity(entries.slice(0, 5)));
      getNotifications({ unread_only: true, limit: 3 }).then(setNotificationsPreview);
    }
    setProfile((prev) => (prev ? { ...prev, ...result.user } : prev));
    if (result.badges_unlocked.length > 0) {
      setUnlockedBanner(`🏅 Badge unlocked: ${result.badges_unlocked.map((b) => b.name).join(", ")}`);
      getAchievements().then(setBadgeSummary);
    }
  }

  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void">
        <p className="font-mono text-sm text-gray-500">Loading command center…</p>
      </main>
    );
  }

  if (loadError || !profile) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void px-4">
        <p className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
          {loadError ?? "Could not load your dashboard."}
        </p>
      </main>
    );
  }

  return (
    <div className="flex h-screen flex-col bg-void">
      <AppNav profile={profile} onLogout={logout} />

      <div className="flex flex-1 overflow-hidden">
        {/* Left sidebar */}
        <aside className="flex w-72 shrink-0 flex-col border-r border-border bg-panel">
          <div className="border-b border-border px-5 py-4">
            <p className="text-sm font-medium text-gray-200">{profile.username}</p>
            <p className="text-xs text-gray-500">{profile.current_role}</p>
          </div>

          <div className="itc-scroll flex-1 space-y-5 overflow-y-auto px-3 py-4">
            {/* Department filters */}
            <nav className="space-y-1">
              {NAV_SECTIONS.map((section) => {
                const isActive = activeDepartment === section.department;
                return (
                  <button
                    key={section.label}
                    onClick={() => setActiveDepartment(section.department)}
                    className={`w-full rounded-lg px-3 py-2 text-left text-sm transition ${
                      isActive ? "bg-accent-dim/40 text-accent" : "text-gray-400 hover:bg-panel-raised hover:text-gray-200"
                    }`}
                  >
                    {section.label}
                  </button>
                );
              })}
            </nav>

            {/* Severity quick filters */}
            <div className="px-3">
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">Severity</p>
              <div className="flex flex-wrap gap-1">
                {SEVERITY_FILTERS.map((f) => (
                  <button
                    key={f.label}
                    onClick={() => setSeverityFilter(f.value)}
                    className={`rounded-lg px-2.5 py-1 text-xs font-medium transition ${
                      severityFilter === f.value
                        ? "bg-accent-dim/40 text-accent"
                        : "bg-panel-raised text-gray-400 hover:text-gray-200"
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Leaderboard snippet */}
            <div className="px-3">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Leaderboard</p>
                <Link href="/leaderboard" className="text-xs text-accent hover:underline">
                  View all
                </Link>
              </div>
              {rank && (
                <p className="mb-2 text-xs text-gray-500">
                  You&apos;re <span className="font-mono text-accent">#{rank.rank}</span> ({rank.value} XP)
                </p>
              )}
              <ul className="space-y-1">
                {topThree.map((entry) => (
                  <li key={entry.user_id} className="flex items-center justify-between text-xs">
                    <span className={entry.user_id === profile.id ? "text-accent" : "text-gray-400"}>
                      #{entry.rank} {entry.username}
                    </span>
                    <span className="font-mono text-gray-500">{entry.value}</span>
                  </li>
                ))}
                {topThree.length === 0 && <li className="text-xs text-gray-600">No ranked users yet.</li>}
              </ul>
            </div>

            {/* Recent activity */}
            <div className="px-3">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Recent Activity</p>
                <Link href="/history" className="text-xs text-accent hover:underline">
                  View all
                </Link>
              </div>
              <ul className="space-y-1.5">
                {recentActivity.map((entry) => (
                  <li key={entry.ticket_id} className="flex items-center justify-between gap-2 text-xs">
                    <span className="truncate text-gray-400">{entry.ticket_title}</span>
                    <span className={entry.status === "Resolved" ? "shrink-0 text-success" : "shrink-0 text-gray-600"}>
                      {entry.status}
                    </span>
                  </li>
                ))}
                {recentActivity.length === 0 && <li className="text-xs text-gray-600">No activity yet.</li>}
              </ul>
            </div>

            {/* Notifications preview */}
            <div className="px-3">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Notifications</p>
                <Link href="/notifications" className="text-xs text-accent hover:underline">
                  View all
                </Link>
              </div>
              <ul className="space-y-1.5">
                {notificationsPreview.map((n) => (
                  <li key={n.id} className="line-clamp-2 text-xs text-gray-400">
                    {n.message}
                  </li>
                ))}
                {notificationsPreview.length === 0 && <li className="text-xs text-gray-600">You&apos;re all caught up.</li>}
              </ul>
            </div>
          </div>

          {/* Badges widget */}
          <Link
            href="/achievements"
            className="border-t border-border px-5 py-3 text-xs text-gray-500 transition hover:bg-panel-raised hover:text-gray-300"
          >
            🏅 {badgeSummary ? `${badgeSummary.filter((b) => b.earned).length}/${badgeSummary.length}` : "…"} badges
            earned
          </Link>
        </aside>

        {/* Main column */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {/* Metrics header */}
          <header className="border-b border-border bg-panel px-6 py-4">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Current IT Tier</p>
                <p className="mt-0.5 font-mono text-sm font-semibold text-accent">{profile.current_role}</p>
              </div>
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <XPBar label="Automation XP" value={profile.automation_xp} colorClass="bg-accent" />
              <XPBar label="Database XP" value={profile.database_xp} colorClass="bg-success" />
              <XPBar label="Networking XP" value={profile.networking_xp} colorClass="bg-warning" />
            </div>
          </header>

          {/* Central feed / workspace */}
          <main className="itc-scroll flex-1 overflow-y-auto p-6">
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
                  mode="learner"
                  onClose={() => {
                    setSelectedTicket(null);
                    setUnlockedBanner(null);
                  }}
                  onResolved={(result) => handleResolved(selectedTicket.id, result)}
                />
              </div>
            ) : (
              <>
                {/* Search */}
                <div className="mb-4">
                  <input
                    type="search"
                    value={searchInput}
                    onChange={(e) => setSearchInput(e.target.value)}
                    placeholder="Search tickets…"
                    className="w-64 rounded-lg border border-border-soft bg-panel-raised px-3 py-2 text-sm text-gray-200 outline-none transition focus:border-accent focus:ring-1 focus:ring-accent"
                  />
                </div>

                <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {visibleTickets.map((ticket) => (
                    <button
                      key={ticket.id}
                      onClick={() => setSelectedTicket(ticket)}
                      className={`flex flex-col items-start rounded-xl border border-border bg-panel text-left transition hover:border-accent/50 hover:bg-panel-raised ${
                        density === "compact" ? "p-3" : "p-4"
                      }`}
                    >
                      <div className="flex w-full items-center justify-between">
                        <span className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-gray-500">
                          <span className={`h-1.5 w-1.5 rounded-full ${SEVERITY_DOT[ticket.severity]}`} />
                          {ticket.severity}
                        </span>
                        {resolvedIds.has(ticket.id) && <span className="text-xs text-success">✓ Resolved</span>}
                      </div>
                      <h3 className="mt-2 text-sm font-semibold text-gray-100">{ticket.title}</h3>
                      <p className="mt-1 text-xs text-gray-500">{ticket.department}</p>
                      {density === "comfortable" && (
                        <p className="mt-3 line-clamp-3 text-xs text-gray-400">{ticket.problem_description}</p>
                      )}
                    </button>
                  ))}
                  {!isFetchingTickets && visibleTickets.length === 0 && (
                    <p className="col-span-full py-12 text-center text-sm text-gray-600">No tickets in this queue.</p>
                  )}
                </div>
              </>
            )}
          </main>
        </div>
      </div>
    </div>
  );
}

/** A labeled XP progress bar. Levels are a display heuristic (100 XP per
 * level) purely for a meaningful bar fill -- the backend has no concept of
 * "levels", only raw XP counters. */
function XPBar({ label, value, colorClass }: { label: string; value: number; colorClass: string }) {
  const level = Math.floor(value / 100) + 1;
  const progressInLevel = value % 100;

  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-gray-400">{label}</span>
        <span className="font-mono text-xs text-gray-500">
          Lvl {level} · {value} XP
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-panel-raised">
        <div className={`h-full rounded-full ${colorClass} transition-all`} style={{ width: `${progressInLevel}%` }} />
      </div>
    </div>
  );
}
