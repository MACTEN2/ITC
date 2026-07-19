/**
 * Thin fetch wrapper + typed helpers for the ITC backend.
 *
 * Auth model: the backend issues a JWT on login (POST /api/auth/login,
 * OAuth2 form-encoded). We keep it in localStorage under `itc_token` and
 * attach it as `Authorization: Bearer <token>` on every subsequent request.
 * This is simple and fine for a learning-tool SPA; it does mean the token is
 * readable by any script on the page (XSS risk) -- a production app with a
 * real threat model would prefer an httpOnly cookie instead.
 */

import type {
  AccountDeletePayload,
  AchievementBadge,
  AdminSubmission,
  AdminSubmissionResponse,
  AdminUser,
  AnalyticsSummary,
  DepartmentStats,
  LeaderboardResponse,
  LeaderboardTrack,
  LoginEvent,
  Notification,
  NotificationPreferences,
  ProfileUpdatePayload,
  PublicUserProfile,
  Severity,
  SubmissionResponse,
  Ticket,
  TicketHistoryEntry,
  TicketSubmissionPayload,
  TokenResponse,
  UserDataExport,
  UserProfile,
} from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const TOKEN_STORAGE_KEY = "itc_token";

// -- Token storage ------------------------------------------------------

export function getToken(): string | null {
  if (typeof window === "undefined") return null; // SSR/build-time guard
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_STORAGE_KEY);
}

// -- Low-level request helper --------------------------------------------

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(options.headers);
  if (!(options.body instanceof URLSearchParams)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    // FastAPI's own HTTPException(detail=...) comes back as a plain string,
    // but a 422 from Pydantic request validation (e.g. password too short,
    // malformed email) comes back as detail: [{ msg, loc, type, ... }] --
    // surface the first validation message instead of a bare "422".
    let detail = `Request failed (${response.status})`;
    if (typeof body?.detail === "string") {
      detail = body.detail;
    } else if (Array.isArray(body?.detail) && typeof body.detail[0]?.msg === "string") {
      detail = body.detail[0].msg;
    }
    throw new ApiError(detail, response.status);
  }

  // 204s and similar have no JSON body to parse.
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

function buildQuery(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

// -- Auth -----------------------------------------------------------------

export async function login(username: string, password: string): Promise<TokenResponse> {
  // The backend's /api/auth/login uses OAuth2PasswordRequestForm, which
  // expects application/x-www-form-urlencoded, not JSON.
  const body = new URLSearchParams({ username, password });
  return apiFetch<TokenResponse>("/api/auth/login", { method: "POST", body });
}

export async function register(username: string, email: string, password: string): Promise<UserProfile> {
  return apiFetch<UserProfile>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, email, password }),
  });
}

export async function getCurrentUser(): Promise<UserProfile> {
  return apiFetch<UserProfile>("/api/auth/me");
}

export async function updateProfile(payload: ProfileUpdatePayload): Promise<UserProfile> {
  return apiFetch<UserProfile>("/api/auth/me", { method: "PATCH", body: JSON.stringify(payload) });
}

export async function deleteAccount(payload: AccountDeletePayload): Promise<void> {
  return apiFetch<void>("/api/auth/me", { method: "DELETE", body: JSON.stringify(payload) });
}

export async function getLoginActivity(limit = 20): Promise<LoginEvent[]> {
  return apiFetch<LoginEvent[]>(`/api/auth/login-activity${buildQuery({ limit })}`);
}

// -- Learner tickets --------------------------------------------------------

export async function getTickets(params?: { department?: string; severity?: Severity; q?: string }): Promise<Ticket[]> {
  return apiFetch<Ticket[]>(`/api/tickets${buildQuery(params ?? {})}`);
}

export async function submitTicket(ticketId: number, form: TicketSubmissionPayload): Promise<SubmissionResponse> {
  return apiFetch<SubmissionResponse>("/api/tickets/submit", {
    method: "POST",
    body: JSON.stringify({ ticket_id: ticketId, ...form }),
  });
}

// -- Admin tickets ------------------------------------------------------------

export async function getAdminTickets(): Promise<Ticket[]> {
  return apiFetch<Ticket[]>("/api/admin/tickets");
}

export async function submitAdminTicket(
  ticketId: number,
  form: TicketSubmissionPayload,
): Promise<AdminSubmissionResponse> {
  return apiFetch<AdminSubmissionResponse>("/api/admin/tickets/submit", {
    method: "POST",
    body: JSON.stringify({ ticket_id: ticketId, ...form }),
  });
}

// -- Ticket history -----------------------------------------------------------

export async function getTicketHistory(params?: { status?: "Open" | "Resolved"; department?: string }): Promise<TicketHistoryEntry[]> {
  return apiFetch<TicketHistoryEntry[]>(`/api/history${buildQuery(params ?? {})}`);
}

// -- Leaderboard ----------------------------------------------------------------

export async function getLeaderboard(track: LeaderboardTrack = "total", limit = 50): Promise<LeaderboardResponse> {
  return apiFetch<LeaderboardResponse>(`/api/leaderboard${buildQuery({ track, limit })}`);
}

// -- Analytics (admin-only) ------------------------------------------------------

export async function getDepartmentStats(): Promise<DepartmentStats[]> {
  return apiFetch<DepartmentStats[]>("/api/analytics/departments");
}

export async function getAnalyticsSummary(): Promise<AnalyticsSummary> {
  return apiFetch<AnalyticsSummary>("/api/analytics/summary");
}

// -- Achievements -----------------------------------------------------------------

export async function getAchievements(): Promise<AchievementBadge[]> {
  return apiFetch<AchievementBadge[]>("/api/achievements");
}

// -- Notifications --------------------------------------------------------------

export async function getNotifications(params?: { unread_only?: boolean; limit?: number }): Promise<Notification[]> {
  return apiFetch<Notification[]>(`/api/notifications${buildQuery(params ?? {})}`);
}

export async function markNotificationRead(id: number): Promise<Notification> {
  return apiFetch<Notification>(`/api/notifications/${id}/read`, { method: "PATCH" });
}

export async function markAllNotificationsRead(): Promise<void> {
  return apiFetch<void>("/api/notifications/read-all", { method: "POST" });
}

export async function getNotificationPreferences(): Promise<NotificationPreferences> {
  return apiFetch<NotificationPreferences>("/api/notifications/preferences");
}

export async function updateNotificationPreferences(
  payload: Partial<NotificationPreferences>,
): Promise<NotificationPreferences> {
  return apiFetch<NotificationPreferences>("/api/notifications/preferences", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

// -- Public profiles --------------------------------------------------------------

export async function getPublicUserProfile(username: string): Promise<PublicUserProfile> {
  return apiFetch<PublicUserProfile>(`/api/users/${encodeURIComponent(username)}`);
}

// -- Data export --------------------------------------------------------------------

export async function exportUserData(): Promise<UserDataExport> {
  return apiFetch<UserDataExport>("/api/export");
}

// -- Admin: user management (view-only) ----------------------------------------------

export async function getAdminUsers(params?: { q?: string; limit?: number; offset?: number }): Promise<AdminUser[]> {
  return apiFetch<AdminUser[]>(`/api/admin/users${buildQuery(params ?? {})}`);
}

// -- Admin: submission audit log ------------------------------------------------------

export async function getAdminSubmissions(params?: {
  user_id?: number;
  ticket_id?: number;
  department?: string;
  status?: "Open" | "Resolved";
  limit?: number;
  offset?: number;
}): Promise<AdminSubmission[]> {
  return apiFetch<AdminSubmission[]>(`/api/admin/submissions${buildQuery(params ?? {})}`);
}
