"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, clearToken, getCurrentUser, getToken } from "@/lib/api";
import type { UserProfile } from "@/lib/types";

/**
 * The auth-gate pattern shared by every protected page: bounce to /login if
 * there's no token, fetch the caller's own profile, and treat a 401 as a
 * genuinely-expired session (clear + redirect) vs. any other error as a
 * transient failure (rendered inline instead of silently logging someone out).
 *
 * `extraFetch` lets a page load its own data (tickets, history, ...) in the
 * same `Promise.all` as the profile fetch, so there's one combined
 * isLoading/loadError state instead of every page re-deriving it.
 */
export function useSession<T = undefined>(extraFetch?: () => Promise<T>) {
  const router = useRouter();

  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [extra, setExtra] = useState<T | undefined>(undefined);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    Promise.all([getCurrentUser(), extraFetch ? extraFetch() : Promise.resolve(undefined as T)])
      .then(([profileResponse, extraResponse]) => {
        setProfile(profileResponse);
        setExtra(extraResponse);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          clearToken();
          router.replace("/login");
          return;
        }
        setLoadError(err instanceof ApiError ? err.message : "Could not reach the ITC server.");
      })
      .finally(() => setIsLoading(false));
    // extraFetch is intentionally excluded -- passing a new function identity every
    // render must not re-trigger the fetch; callers control refetching explicitly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  function logout() {
    clearToken();
    router.replace("/login");
  }

  return { profile, setProfile, extra, isLoading, loadError, logout };
}
