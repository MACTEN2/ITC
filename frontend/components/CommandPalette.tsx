"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getAchievements, getTickets, getTicketHistory } from "@/lib/api";
import type { AchievementBadge, Ticket, TicketHistoryEntry, UserProfile } from "@/lib/types";

interface CommandPaletteProps {
  profile: UserProfile;
  isOpen: boolean;
  onClose: () => void;
}

interface Destination {
  label: string;
  href: string;
  adminOnly?: boolean;
}

const DESTINATIONS: Destination[] = [
  { label: "Dashboard", href: "/dashboard" },
  { label: "Leaderboard", href: "/leaderboard" },
  { label: "History", href: "/history" },
  { label: "Achievements", href: "/achievements" },
  { label: "Notifications", href: "/notifications" },
  { label: "Profile", href: "/profile" },
  { label: "Settings", href: "/settings" },
  { label: "Admin Panel", href: "/admin", adminOnly: true },
  { label: "Analytics", href: "/analytics", adminOnly: true },
  { label: "Admin: Users", href: "/admin/users", adminOnly: true },
  { label: "Admin: Submissions Audit Log", href: "/admin/submissions", adminOnly: true },
];

interface ResultItem {
  key: string;
  section: "Pages" | "Tickets" | "History" | "Achievements";
  label: string;
  sublabel?: string;
  onSelect: () => void;
}

/**
 * Combined global search + Cmd/Ctrl+K quick-nav popup, mounted once in AppNav
 * so it's available on every authenticated page. Static page destinations are
 * substring-matched instantly; ticket content is a debounced live backend
 * search (reusing GET /api/tickets's `q` param); history/achievements are
 * fetched once when the palette opens and filtered client-side per keystroke
 * (both are small, per-user datasets -- no need to refetch on every key).
 */
export default function CommandPalette({ profile, isOpen, onClose }: CommandPaletteProps) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);

  const [query, setQuery] = useState("");
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [history, setHistory] = useState<TicketHistoryEntry[]>([]);
  const [achievements, setAchievements] = useState<AchievementBadge[]>([]);
  const [highlightedIndex, setHighlightedIndex] = useState(0);

  useEffect(() => {
    if (!isOpen) return;
    setQuery("");
    setHighlightedIndex(0);
    getTicketHistory().then(setHistory);
    getAchievements().then(setAchievements);
    inputRef.current?.focus();
  }, [isOpen]);

  // Debounced live ticket search -- only fires with a non-empty query.
  useEffect(() => {
    if (!isOpen || !query.trim()) {
      setTickets([]);
      return;
    }
    const handle = setTimeout(() => {
      getTickets({ q: query.trim() }).then((results) => setTickets(results.slice(0, 5)));
    }, 250);
    return () => clearTimeout(handle);
  }, [isOpen, query]);

  const results: ResultItem[] = useMemo(() => {
    const needle = query.trim().toLowerCase();

    const pageMatches: ResultItem[] = DESTINATIONS.filter((d) => !d.adminOnly || profile.is_admin)
      .filter((d) => d.label.toLowerCase().includes(needle))
      .map((d) => ({
        key: `page-${d.href}`,
        section: "Pages",
        label: d.label,
        onSelect: () => router.push(d.href),
      }));

    const ticketMatches: ResultItem[] = tickets.map((t) => ({
      key: `ticket-${t.id}`,
      section: "Tickets",
      label: t.title,
      sublabel: t.department,
      onSelect: () => router.push(`/dashboard?ticket=${t.id}`),
    }));

    const historyMatches: ResultItem[] = needle
      ? history
          .filter((h) => h.ticket_title.toLowerCase().includes(needle))
          .slice(0, 5)
          .map((h) => ({
            key: `history-${h.ticket_id}`,
            section: "History",
            label: h.ticket_title,
            sublabel: h.status,
            onSelect: () => router.push("/history"),
          }))
      : [];

    const achievementMatches: ResultItem[] = needle
      ? achievements
          .filter((a) => a.name.toLowerCase().includes(needle) || a.description.toLowerCase().includes(needle))
          .slice(0, 5)
          .map((a) => ({
            key: `badge-${a.id}`,
            section: "Achievements",
            label: a.name,
            sublabel: a.earned ? "Earned" : "Locked",
            onSelect: () => router.push("/achievements"),
          }))
      : [];

    return [...pageMatches, ...ticketMatches, ...historyMatches, ...achievementMatches];
  }, [query, tickets, history, achievements, profile.is_admin, router]);

  function selectAndClose(item: ResultItem) {
    item.onSelect();
    onClose();
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Escape") {
      onClose();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightedIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && results[highlightedIndex]) {
      selectAndClose(results[highlightedIndex]);
    }
  }

  if (!isOpen) return null;

  let sectionCursor = -1;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-void/70 pt-24" onClick={onClose}>
      <div
        className="w-full max-w-lg overflow-hidden rounded-xl border border-border bg-panel shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setHighlightedIndex(0);
          }}
          onKeyDown={handleKeyDown}
          placeholder="Search pages, tickets, history, achievements…"
          className="w-full border-b border-border bg-transparent px-4 py-3 text-sm text-gray-200 outline-none placeholder:text-gray-600"
        />
        <div className="itc-scroll max-h-80 overflow-y-auto py-2">
          {results.length === 0 && <p className="px-4 py-6 text-center text-sm text-gray-600">No matches.</p>}
          {(["Pages", "Tickets", "History", "Achievements"] as const).map((section) => {
            const sectionResults = results.filter((r) => r.section === section);
            if (sectionResults.length === 0) return null;
            return (
              <div key={section}>
                <p className="px-4 pt-2 pb-1 text-xs font-medium uppercase tracking-wide text-gray-500">{section}</p>
                {sectionResults.map((item) => {
                  sectionCursor += 1;
                  const isHighlighted = sectionCursor === highlightedIndex;
                  return (
                    <button
                      key={item.key}
                      onClick={() => selectAndClose(item)}
                      onMouseEnter={() => setHighlightedIndex(sectionCursor)}
                      className={`flex w-full items-center justify-between px-4 py-2 text-left text-sm transition ${
                        isHighlighted ? "bg-accent-dim/40 text-accent" : "text-gray-300"
                      }`}
                    >
                      <span>{item.label}</span>
                      {item.sublabel && <span className="text-xs text-gray-500">{item.sublabel}</span>}
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
