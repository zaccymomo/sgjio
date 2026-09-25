import { createContext, useContext } from "react";

export type User = {
  id: string;
  name: string;
  email: string;
  role: "user" | "admin";
  user_type: "newcomer" | "singaporean" | null;
  created_at: string;
};

export type AuthStatus = "loading" | "signed-in" | "signed-out" | "error";

export type AuthContextValue = {
  status: AuthStatus;
  user: User | null;
  signIn: (email: string, password: string) => Promise<User>;
  signOut: () => Promise<void>;
  /** Re-check with the server, e.g. after "Try again". */
  refresh: () => Promise<void>;
};

export const AuthContext = createContext<AuthContextValue | null>(null);

/** Current sign-in state. Use inside <AuthProvider>. */
export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}

/**
 * The page to return to after signing in. Only same-site paths are allowed, so a crafted
 * link cannot send someone to another website after they sign in.
 */
export function safeNextPath(next: string | null, fallback = "/"): string {
  if (!next || !next.startsWith("/") || next.startsWith("//")) return fallback;
  return next;
}
