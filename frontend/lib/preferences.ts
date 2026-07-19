/**
 * Client-only display preferences (default department filter, ticket-card
 * density) and the light/dark theme -- all localStorage-backed, no backend
 * involvement. Kept in one module, parallel to the token helpers in api.ts,
 * since every page that needs one of these reads it directly rather than
 * going through any shared React state (this app has no global session
 * context by design -- see lib/useSession.ts).
 */

export type Density = "comfortable" | "compact";
export type Theme = "dark" | "light";

const PREFERENCES_KEY = "itc_display_preferences";
const THEME_KEY = "itc_theme";

interface DisplayPreferences {
  defaultDepartment: string | null;
  density: Density;
}

const DEFAULT_PREFERENCES: DisplayPreferences = {
  defaultDepartment: null,
  density: "comfortable",
};

export function getDisplayPreferences(): DisplayPreferences {
  if (typeof window === "undefined") return DEFAULT_PREFERENCES;
  try {
    const raw = window.localStorage.getItem(PREFERENCES_KEY);
    if (!raw) return DEFAULT_PREFERENCES;
    return { ...DEFAULT_PREFERENCES, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

export function setDisplayPreferences(update: Partial<DisplayPreferences>): DisplayPreferences {
  const next = { ...getDisplayPreferences(), ...update };
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify(next));
    } catch {
      // Storage unavailable (private mode, quota, etc.) -- preference just won't persist.
    }
  }
  return next;
}

export function getTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  try {
    return window.localStorage.getItem(THEME_KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

export function setTheme(theme: Theme): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch {
    // Storage unavailable -- theme still applies for this page load via applyTheme().
  }
  applyTheme(theme);
}

export function applyTheme(theme: Theme): void {
  if (typeof document === "undefined") return;
  if (theme === "light") {
    document.documentElement.setAttribute("data-theme", "light");
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
}
