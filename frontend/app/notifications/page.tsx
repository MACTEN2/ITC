"use client";

import { useState } from "react";
import { getNotifications, markAllNotificationsRead, markNotificationRead } from "@/lib/api";
import { useSession } from "@/lib/useSession";
import AppNav from "@/components/AppNav";
import type { Notification } from "@/lib/types";

const TYPE_ICON: Record<string, string> = {
  ticket_resolved: "✅",
  badge_unlocked: "🏅",
};

function NotificationRow({ notification }: { notification: Notification }) {
  const [isRead, setIsRead] = useState(notification.is_read);

  return (
    <button
      onClick={async () => {
        if (isRead) return;
        await markNotificationRead(notification.id);
        setIsRead(true);
      }}
      className={`flex w-full items-start gap-3 rounded-xl border px-4 py-3 text-left transition ${
        isRead ? "border-border bg-panel" : "border-accent/40 bg-accent-dim/10"
      }`}
    >
      <span className="text-lg">{TYPE_ICON[notification.type] ?? "🔔"}</span>
      <div className="flex-1">
        <p className="text-sm text-gray-200">{notification.message}</p>
        <p className="mt-1 text-xs text-gray-500">{new Date(notification.created_at).toLocaleString()}</p>
      </div>
      {!isRead && <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-accent" />}
    </button>
  );
}

export default function NotificationsPage() {
  const { profile, extra: notifications, isLoading, loadError, logout } = useSession<Notification[]>(getNotifications);
  const [isMarkingAllRead, setIsMarkingAllRead] = useState(false);

  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void">
        <p className="font-mono text-sm text-gray-500">Loading notifications…</p>
      </main>
    );
  }

  if (loadError || !profile) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void px-4">
        <p className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
          {loadError ?? "Could not load notifications."}
        </p>
      </main>
    );
  }

  async function handleMarkAllRead() {
    setIsMarkingAllRead(true);
    await markAllNotificationsRead();
    window.location.reload();
  }

  return (
    <div className="flex h-screen flex-col bg-void">
      <AppNav profile={profile} onLogout={logout} />

      <main className="itc-scroll mx-auto w-full max-w-2xl flex-1 overflow-y-auto p-6">
        <div className="mb-4 flex items-center justify-between">
          <h1 className="text-lg font-semibold text-gray-100">Notifications</h1>
          <button
            onClick={handleMarkAllRead}
            disabled={isMarkingAllRead}
            className="rounded-lg bg-panel-raised px-3 py-1.5 text-xs font-medium text-gray-300 transition hover:bg-border disabled:opacity-50"
          >
            Mark all read
          </button>
        </div>

        <div className="space-y-2">
          {notifications?.map((n) => (
            <NotificationRow key={n.id} notification={n} />
          ))}
          {notifications && notifications.length === 0 && (
            <p className="py-12 text-center text-sm text-gray-600">No notifications yet.</p>
          )}
        </div>
      </main>
    </div>
  );
}
