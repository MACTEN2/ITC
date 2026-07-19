"use client";

import { useState } from "react";
import { ApiError, updateProfile } from "@/lib/api";
import { useSession } from "@/lib/useSession";
import AppNav from "@/components/AppNav";

export default function ProfilePage() {
  const { profile, setProfile, isLoading, loadError, logout } = useSession();

  const [email, setEmail] = useState("");
  const [emailStatus, setEmailStatus] = useState<{ ok: boolean; message: string } | null>(null);
  const [isSavingEmail, setIsSavingEmail] = useState(false);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordStatus, setPasswordStatus] = useState<{ ok: boolean; message: string } | null>(null);
  const [isSavingPassword, setIsSavingPassword] = useState(false);

  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void">
        <p className="font-mono text-sm text-gray-500">Loading profile…</p>
      </main>
    );
  }

  if (loadError || !profile) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void px-4">
        <p className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
          {loadError ?? "Could not load your profile."}
        </p>
      </main>
    );
  }

  async function handleEmailSave() {
    setIsSavingEmail(true);
    setEmailStatus(null);
    try {
      const updated = await updateProfile({ email });
      setProfile((prev) => (prev ? { ...prev, ...updated } : prev));
      setEmailStatus({ ok: true, message: "Email updated." });
      setEmail("");
    } catch (err) {
      setEmailStatus({ ok: false, message: err instanceof ApiError ? err.message : "Could not update email." });
    } finally {
      setIsSavingEmail(false);
    }
  }

  async function handlePasswordSave() {
    if (newPassword !== confirmPassword) {
      setPasswordStatus({ ok: false, message: "New password and confirmation do not match." });
      return;
    }
    setIsSavingPassword(true);
    setPasswordStatus(null);
    try {
      await updateProfile({ current_password: currentPassword, new_password: newPassword });
      setPasswordStatus({ ok: true, message: "Password changed." });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      setPasswordStatus({ ok: false, message: err instanceof ApiError ? err.message : "Could not change password." });
    } finally {
      setIsSavingPassword(false);
    }
  }

  return (
    <div className="flex h-screen flex-col bg-void">
      <AppNav profile={profile} onLogout={logout} />

      <main className="itc-scroll mx-auto w-full max-w-2xl flex-1 overflow-y-auto p-6">
        <h1 className="text-lg font-semibold text-gray-100">Account Settings</h1>

        {/* Account info */}
        <section className="mt-6 rounded-xl border border-border bg-panel p-6">
          <h2 className="text-sm font-semibold text-gray-100">Account Info</h2>
          <dl className="mt-4 grid grid-cols-1 gap-x-4 gap-y-3 font-mono text-xs sm:grid-cols-2">
            <div>
              <dt className="text-gray-500">USERNAME</dt>
              <dd className="mt-0.5 text-gray-200">{profile.username}</dd>
            </div>
            <div>
              <dt className="text-gray-500">ROLE</dt>
              <dd className="mt-0.5 text-gray-200">{profile.current_role}</dd>
            </div>
            <div>
              <dt className="text-gray-500">MEMBER SINCE</dt>
              <dd className="mt-0.5 text-gray-200">{new Date(profile.created_at).toLocaleDateString()}</dd>
            </div>
            <div>
              <dt className="text-gray-500">TOTAL XP</dt>
              <dd className="mt-0.5 text-accent">
                {profile.networking_xp + profile.automation_xp + profile.database_xp} XP
                {profile.infra_points > 0 && ` · ${profile.infra_points} infra points`}
              </dd>
            </div>
          </dl>

          <div className="mt-6">
            <label htmlFor="email" className="mb-2 block text-xs font-medium uppercase tracking-wide text-gray-500">
              Email
            </label>
            <div className="flex gap-2">
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={profile.email}
                className="flex-1 rounded-lg border border-border-soft bg-panel-raised px-3 py-2 text-sm text-gray-200 outline-none transition focus:border-accent focus:ring-1 focus:ring-accent"
              />
              <button
                onClick={handleEmailSave}
                disabled={!email || isSavingEmail}
                className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-void transition hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isSavingEmail ? "Saving…" : "Save"}
              </button>
            </div>
            {emailStatus && (
              <p className={`mt-2 text-xs ${emailStatus.ok ? "text-success" : "text-danger"}`}>{emailStatus.message}</p>
            )}
          </div>
        </section>

        {/* Change password */}
        <section className="mt-6 rounded-xl border border-border bg-panel p-6">
          <h2 className="text-sm font-semibold text-gray-100">Change Password</h2>
          <div className="mt-4 space-y-3">
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              placeholder="Current password"
              className="w-full rounded-lg border border-border-soft bg-panel-raised px-3 py-2 text-sm text-gray-200 outline-none transition focus:border-accent focus:ring-1 focus:ring-accent"
            />
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="New password (min 8 characters)"
              className="w-full rounded-lg border border-border-soft bg-panel-raised px-3 py-2 text-sm text-gray-200 outline-none transition focus:border-accent focus:ring-1 focus:ring-accent"
            />
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Confirm new password"
              className="w-full rounded-lg border border-border-soft bg-panel-raised px-3 py-2 text-sm text-gray-200 outline-none transition focus:border-accent focus:ring-1 focus:ring-accent"
            />
            <button
              onClick={handlePasswordSave}
              disabled={!currentPassword || !newPassword || isSavingPassword}
              className="w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-void transition hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isSavingPassword ? "Saving…" : "Change Password"}
            </button>
            {passwordStatus && (
              <p className={`text-xs ${passwordStatus.ok ? "text-success" : "text-danger"}`}>{passwordStatus.message}</p>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
