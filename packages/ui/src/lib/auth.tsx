/**
 * Sign-in state for either front end (SCRUM-73).
 *
 * Wrap an app in <AuthProvider basePath="/api/auth"> (main app) or
 * <AuthProvider basePath="/api/admin/auth"> (admin portal), then:
 *
 *   const { user, signIn, signOut } = useAuth();
 *
 * and protect routes with <RequireAuth />, which sends signed-out visitors to the
 * sign-in page with ?next= set to the page they wanted (SCRUM-62 AC7, SCRUM-68 AC6).
 */
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { FullPageSpinner } from "../components/Spinner";
import { ApiError, apiFetch } from "./api";
import { AuthContext, useAuth, type AuthStatus, type User } from "./auth-context";

type AuthState = { status: AuthStatus; user: User | null };

export function AuthProvider({ basePath, children }: { basePath: string; children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading", user: null });

  const loadCurrentUser = useCallback(async (): Promise<AuthState> => {
    try {
      return { status: "signed-in", user: await apiFetch<User>(`${basePath}/me`) };
    } catch (error) {
      const signedOut = error instanceof ApiError && error.status === 401;
      return { status: signedOut ? "signed-out" : "error", user: null };
    }
  }, [basePath]);

  // Ask the server who is signed in when the app starts.
  useEffect(() => {
    let active = true;
    void loadCurrentUser().then((next) => {
      if (active) setState(next);
    });
    return () => {
      active = false;
    };
  }, [loadCurrentUser]);

  const refresh = useCallback(async () => {
    setState({ status: "loading", user: null });
    setState(await loadCurrentUser());
  }, [loadCurrentUser]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      const result = await apiFetch<{ user: User }>(`${basePath}/sign-in`, {
        method: "POST",
        body: { email, password },
      });
      setState({ status: "signed-in", user: result.user });
      return result.user;
    },
    [basePath],
  );

  const signOut = useCallback(async () => {
    await apiFetch<void>(`${basePath}/sign-out`, { method: "POST" });
    setState({ status: "signed-out", user: null });
  }, [basePath]);

  const value = useMemo(
    () => ({ ...state, signIn, signOut, refresh }),
    [state, signIn, signOut, refresh],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** Route guard. Renders child routes only when signed in. */
export function RequireAuth({ signInPath = "/sign-in" }: { signInPath?: string }) {
  const { status, refresh } = useAuth();
  const location = useLocation();

  if (status === "loading") return <FullPageSpinner />;
  if (status === "error") {
    return (
      <ErrorState
        message="We couldn't check whether you're signed in."
        onRetry={() => void refresh()}
      />
    );
  }
  if (status === "signed-out") {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`${signInPath}?next=${next}`} replace />;
  }
  return <Outlet />;
}
