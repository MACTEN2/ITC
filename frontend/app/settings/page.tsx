"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  clearToken,
  deleteAccount,
  exportUserData,
  getLoginActivity,
  getNotificationPreferences,
  updateNotificationPreferences,
} from "@/lib/api";
import type { LoginEvent, NotificationPreferences } from "@/lib/types";
import { getDisplayPreferences, getTheme, setDisplayPreferences, setTheme, type Density, type Theme } from "@/lib/preferences";
import { useSession } from "@/lib/useSession";
import AppNav from "@/components/AppNav";

const DEPARTMENTS = [
  { label: "All Tickets", value: "" },
  { label: "Help Desk", value: "Help Desk" },
  { label: "Network Operations", value: "Network Operations" },
  { label: "Database Administration", value: "Database Administration" },
];

function Toggle({ enabled, onChange }: { enabled: boolean; onChange: (next: boolean) => void }) {
  return (
    <button
      role="switch"
      aria-checked={enabled}
      onClick={() => onChange(!enabled)}
      className={`h-6 w-11 shrink-0 rounded-full transition ${enabled ? "bg-accent" : "bg-panel-raised"}`}
    >
      <span
        className={`block h-5 w-5 translate-y-0.5 rounded-full bg-void transition ${
          enabled ? "translate-x-5" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}

export default function SettingsPage() {
  const router = useRouter();
  const { profile, isLoading, loadError, logout } = useSession();

  const [preferences, setPreferences] = useState<NotificationPreferences | null>(null);
  const [theme, setThemeState] = useState<Theme>("dark");
  const [defaultDepartment, setDefaultDepartmentState] = useState("");
  const [density, setDensityState] = useState<Density>("comfortable");
  const [loginActivity, setLoginActivity] = useState<LoginEvent[]>([]);

  const [deletePassword, setDeletePassword] = useState("");
  const [deleteConfirming, setDeleteConfirming] = useState(false);
  const [deleteStatus, setDeleteStatus] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    if (!profile) return;
    getNotificationPreferences().then(setPreferences);
    getLoginActivity().then(setLoginActivity);
    setThemeState(getTheme());
    const display = getDisplayPreferences();
    setDefaultDepartmentState(display.defaultDepartment ?? "");
    setDensityState(display.density);
  }, [profile]);

  function handleThemeChange(next: Theme) {
    setThemeState(next);
    setTheme(next);
  }

  function handleDepartmentChange(value: string) {
    setDefaultDepartmentState(value);
    setDisplayPreferences({ defaultDepartment: value || null });
  }

  function handleDensityChange(value: Density) {
    setDensityState(value);
    setDisplayPreferences({ density: value });
  }

  async function handlePreferenceToggle(field: keyof NotificationPreferences, value: boolean) {
    setPreferences((prev) => (prev ? { ...prev, [field]: value } : prev));
    await updateNotificationPreferences({ [field]: value });
  }

  async function handleExport() {
    const data = await exportUserData();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `itc-export-${profile?.username ?? "account"}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function handleDeleteAccount() {
    setIsDeleting(true);
    setDeleteStatus(null);
    try {
      await deleteAccount({ current_password: deletePassword });
      clearToken();
      router.replace("/register");
    } catch (err) {
      setDeleteStatus(err instanceof ApiError ? err.message : "Could not delete account.");
      setIsDeleting(false);
    }
  }

  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void">
        <p className="font-mono text-sm text-gray-500">Loading settings…</p>
      </main>
    );
  }

  if (loadError || !profile) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void px-4">
        <p className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
          {loadError ?? "Could not load settings."}
        </p>
      </main>
    );
  }

  return (
    <div className="flex h-screen flex-col bg-void">
      <AppNav profile={profile} onLogout={logout} />

      <main className="itc-scroll mx-auto w-full max-w-2xl flex-1 overflow-y-auto p-6">
        <h1 className="text-lg font-semibold text-gray-100">Settings</h1>

        {/* Appearance */}
        <section className="mt-6 rounded-xl border border-border bg-panel p-6">
          <h2 className="text-sm font-semibold text-gray-100">Appearance</h2>
          <div className="mt-4 flex items-center justify-between">
            <span className="text-sm text-gray-300">Theme</span>
            <div className="flex gap-1">
              {(["dark", "light"] as const).map((option) => (
                <button
                  key={option}
                  onClick={() => handleThemeChange(option)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium capitalize transition ${
                    theme === option ? "bg-accent-dim/40 text-accent" : "bg-panel-raised text-gray-400"
                  }`}
                >
                  {option}
                </button>
              ))}
            </div>
          </div>
        </section>

        {/* Display preferences */}
        <section className="mt-6 rounded-xl border border-border bg-panel p-6">
          <h2 className="text-sm font-semibold text-gray-100">Display Preferences</h2>
          <div className="mt-4 flex items-center justify-between">
            <span className="text-sm text-gray-300">Default dashboard filter</span>
            <select
              value={defaultDepartment}
              onChange={(e) => handleDepartmentChange(e.target.value)}
              className="rounded-lg border border-border-soft bg-panel-raised px-3 py-1.5 text-sm text-gray-200 outline-none"
            >
              {DEPARTMENTS.map((d) => (
                <option key={d.label} value={d.value}>
                  {d.label}
                </option>
              ))}
            </select>
          </div>
          <div className="mt-4 flex items-center justify-between">
            <span className="text-sm text-gray-300">Ticket card density</span>
            <div className="flex gap-1">
              {(["comfortable", "compact"] as const).map((option) => (
                <button
                  key={option}
                  onClick={() => handleDensityChange(option)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium capitalize transition ${
                    density === option ? "bg-accent-dim/40 text-accent" : "bg-panel-raised text-gray-400"
                  }`}
                >
                  {option}
                </button>
              ))}
            </div>
          </div>
        </section>

        {/* Notification preferences */}
        <section className="mt-6 rounded-xl border border-border bg-panel p-6">
          <h2 className="text-sm font-semibold text-gray-100">Notification Preferences</h2>
          {preferences && (
            <div className="mt-4 space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-300">Notify when a ticket is resolved</span>
                <Toggle
                  enabled={preferences.notify_ticket_resolved}
                  onChange={(v) => handlePreferenceToggle("notify_ticket_resolved", v)}
                />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-300">Notify when a badge is unlocked</span>
                <Toggle
                  enabled={preferences.notify_badge_unlocked}
                  onChange={(v) => handlePreferenceToggle("notify_badge_unlocked", v)}
                />
              </div>
            </div>
          )}
        </section>

        {/* Recent sign-ins */}
        <section className="mt-6 rounded-xl border border-border bg-panel p-6">
          <h2 className="text-sm font-semibold text-gray-100">Recent Sign-Ins</h2>
          <ul className="mt-4 space-y-2">
            {loginActivity.map((event) => (
              <li key={event.id} className="flex items-center justify-between text-xs">
                <span className="font-mono text-gray-400">{event.ip_address ?? "unknown IP"}</span>
                <span className="text-gray-500">{new Date(event.created_at).toLocaleString()}</span>
              </li>
            ))}
            {loginActivity.length === 0 && <li className="text-xs text-gray-600">No sign-in history yet.</li>}
          </ul>
        </section>

        {/* Data export */}
        <section className="mt-6 rounded-xl border border-border bg-panel p-6">
          <h2 className="text-sm font-semibold text-gray-100">Data Export</h2>
          <p className="mt-2 text-xs text-gray-500">
            Download your profile, ticket history, and achievements as a JSON file.
          </p>
          <button
            onClick={handleExport}
            className="mt-4 rounded-lg bg-panel-raised px-4 py-2 text-sm font-medium text-gray-200 transition hover:bg-border"
          >
            Export my data
          </button>
        </section>

        {/* Danger zone */}
        <section className="mt-6 rounded-xl border border-danger/30 bg-danger/5 p-6">
          <h2 className="text-sm font-semibold text-danger">Danger Zone</h2>
          <p className="mt-2 text-xs text-gray-500">
            Permanently delete your account and all progress. This cannot be undone.
          </p>
          {!deleteConfirming ? (
            <button
              onClick={() => setDeleteConfirming(true)}
              className="mt-4 rounded-lg border border-danger/30 bg-danger/10 px-4 py-2 text-sm font-medium text-danger transition hover:bg-danger/20"
            >
              Delete My Account
            </button>
          ) : (
            <div className="mt-4 space-y-3">
              <input
                type="password"
                value={deletePassword}
                onChange={(e) => setDeletePassword(e.target.value)}
                placeholder="Confirm your password"
                className="w-full rounded-lg border border-danger/30 bg-panel-raised px-3 py-2 text-sm text-gray-200 outline-none"
              />
              <div className="flex gap-2">
                <button
                  onClick={handleDeleteAccount}
                  disabled={!deletePassword || isDeleting}
                  className="rounded-lg bg-danger px-4 py-2 text-sm font-semibold text-void transition hover:bg-danger/80 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isDeleting ? "Deleting…" : "Confirm Permanent Deletion"}
                </button>
                <button
                  onClick={() => {
                    setDeleteConfirming(false);
                    setDeletePassword("");
                    setDeleteStatus(null);
                  }}
                  className="rounded-lg bg-panel-raised px-4 py-2 text-sm font-medium text-gray-200 transition hover:bg-border"
                >
                  Cancel
                </button>
              </div>
              {deleteStatus && <p className="text-xs text-danger">{deleteStatus}</p>}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
