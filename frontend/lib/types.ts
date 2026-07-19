/**
 * TypeScript mirrors of the ITC FastAPI response models. Keep these in sync
 * with the Pydantic schemas in app/main.py, app/routes/auth.py, and
 * app/routes/admin.py -- there is no shared codegen between the two, so a
 * backend field rename needs a matching edit here.
 */

export type Severity = "Low" | "Incident" | "Catastrophic";

// Shared by both the learner catalog (GET /api/tickets) and the admin
// catalog (GET /api/admin/tickets) -- the two endpoints just filter which
// tier of the same underlying `tickets` table they return.
//
// Tickets are resolved by filling out a diagnostic form, not by writing
// code: `root_cause_options` is a single-select list, `resolution_options`
// is a multi-select checklist. Neither list indicates which choice is
// correct -- the answer key lives only in the backend's app/tickets_db.py.
export interface Ticket {
  id: number;
  title: string;
  department: string;
  severity: Severity;
  problem_description: string;
  root_cause_options: string[];
  resolution_options: string[];
  logs_context: Record<string, unknown>;
  validation_criteria: Record<string, unknown>;
}

// A learner's/admin's filled-out resolution form, sent to
// POST /api/tickets/submit or /api/admin/tickets/submit.
export interface TicketSubmissionPayload {
  root_cause: string;
  resolution_actions: string[];
  resolution_notes: string;
}

// -- Auth -------------------------------------------------------------------

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserProfile {
  id: number;
  username: string;
  email: string;
  current_role: string;
  is_admin: boolean;
  networking_xp: number;
  automation_xp: number;
  database_xp: number;
  infra_points: number;
  created_at: string;
}

// -- Learner ticket submission (POST /api/tickets/submit) -------------------

export interface UserXP {
  current_role: string;
  networking_xp: number;
  automation_xp: number;
  database_xp: number;
}

export interface SubmissionResponse {
  passed: boolean;
  message: string;
  details: string[];
  xp_awarded: number;
  resolution_time: number;
  user: UserXP;
  badges_unlocked: Badge[];
}

// -- Admin ticket submission (POST /api/admin/tickets/submit) ---------------

export interface AdminUserStats {
  current_role: string;
  infra_points: number;
}

export interface AdminSubmissionResponse {
  passed: boolean;
  message: string;
  details: string[];
  infra_points_awarded: number;
  resolution_time: number;
  user: AdminUserStats;
  badges_unlocked: Badge[];
}

// A TicketResolutionWorkspace instance grades either tier; this union lets
// callers handle both result shapes without two near-duplicate components.
export type GradingResult = SubmissionResponse | AdminSubmissionResponse;

export function isAdminResult(result: GradingResult): result is AdminSubmissionResponse {
  return "infra_points_awarded" in result;
}

// A badge unlocked by a submission (see submission_response.badges_unlocked) or
// listed in the full catalog (GET /api/achievements).
export interface Badge {
  id: string;
  name: string;
  description: string;
  icon: string;
}

// -- Achievements (GET /api/achievements) ------------------------------------

export interface AchievementBadge extends Badge {
  earned: boolean;
  earned_at: string | null;
}

// -- Ticket history (GET /api/history) ---------------------------------------

export interface TicketHistoryEntry {
  ticket_id: number;
  ticket_title: string;
  department: string;
  severity: Severity;
  status: "Open" | "Resolved";
  unlocked_at: string;
  resolved_at: string | null;
  reward_field: string | null;
  reward_amount: number | null;
}

// -- Leaderboard (GET /api/leaderboard) ---------------------------------------

export type LeaderboardTrack = "total" | "networking" | "automation" | "database" | "infra_points";

export interface LeaderboardEntry {
  rank: number;
  user_id: number;
  username: string;
  current_role: string;
  value: number;
  is_admin: boolean;
}

export interface RankInfo {
  rank: number;
  value: number;
}

export interface LeaderboardResponse {
  track: LeaderboardTrack;
  entries: LeaderboardEntry[];
  your_rank: RankInfo | null;
}

// -- Analytics (admin-only, GET /api/analytics/*) ------------------------------

export interface DepartmentStats {
  department: string;
  ticket_count: number;
  total_attempts: number;
  resolved_count: number;
  resolution_rate: number;
  unique_learners_engaged: number;
}

export interface AnalyticsSummary {
  total_users: number;
  total_tickets_resolved: number;
  average_resolution_rate: number;
  most_active_department: string | null;
  total_badges_unlocked: number;
}

// -- Notifications (GET/PATCH /api/notifications*) -----------------------------

export interface Notification {
  id: number;
  type: string;
  message: string;
  is_read: boolean;
  created_at: string;
}

// -- Profile update (PATCH /api/auth/me) ---------------------------------------

export interface ProfileUpdatePayload {
  email?: string;
  current_password?: string;
  new_password?: string;
}

// -- Account deletion (DELETE /api/auth/me) ------------------------------------

export interface AccountDeletePayload {
  current_password: string;
}

// -- Notification preferences (GET/PATCH /api/notifications/preferences) ------

export interface NotificationPreferences {
  notify_ticket_resolved: boolean;
  notify_badge_unlocked: boolean;
}

// -- Login activity (GET /api/auth/login-activity) ----------------------------

export interface LoginEvent {
  id: number;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
}

// -- Data export (GET /api/export) ---------------------------------------------

export interface UserDataExport {
  exported_at: string;
  profile: UserProfile;
  history: TicketHistoryEntry[];
  achievements: AchievementBadge[];
}

// -- Public profile (GET /api/users/{username}) --------------------------------

export interface PublicUserProfile {
  id: number;
  username: string;
  current_role: string;
  is_admin: boolean;
  networking_xp: number;
  automation_xp: number;
  database_xp: number;
  infra_points: number;
  created_at: string;
  badges: AchievementBadge[];
}

// -- Admin: user management (GET /api/admin/users, view-only) -----------------

export interface AdminUser {
  id: number;
  username: string;
  email: string;
  current_role: string;
  is_admin: boolean;
  networking_xp: number;
  automation_xp: number;
  database_xp: number;
  infra_points: number;
  created_at: string;
  resolved_ticket_count: number;
  badges_earned: number;
}

// -- Admin: submission audit log (GET /api/admin/submissions) -----------------

export interface AdminSubmission {
  user_id: number;
  username: string;
  ticket_id: number;
  ticket_title: string;
  department: string;
  status: "Open" | "Resolved";
  root_cause: string | null;
  resolution_actions: string[];
  resolution_notes: string | null;
  unlocked_at: string;
  resolved_at: string | null;
}
