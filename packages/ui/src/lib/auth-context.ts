import { createContext, useContext } from "react";

/** Self-reported at registration (SCRUM-61). Administrators have none. */
export type UserType = "newcomer" | "singaporean";

export type User = {
  id: string;
  name: string;
  email: string;
  role: "user" | "admin";
  user_type: UserType | null;
  created_at: string;
  /** False for an account created with Google, which signs in with Google only (SCRUM-92). */
  has_password: boolean;
  google_linked: boolean;
  /** Empty until the introduction is finished or skipped; until then it is shown (SCRUM-94). */
  intro_finished_at: string | null;
};

/** What the register form sends. Field names match the API (SCRUM-61). */
export type RegisterInput = {
  name: string;
  email: string;
  password: string;
  password_confirmation: string;
  user_type: UserType;
  privacy_consent: boolean;
  privacy_notice_version: string;
};

/** The sign-up step for someone new who continued with Google (SCRUM-92). */
export type GoogleSignupInput = {
  name: string;
  user_type: UserType;
  privacy_consent: boolean;
  privacy_notice_version: string;
};

/** Signed in, or new to SGJio: the name and email to greet them with at sign-up. */
export type GoogleSignInResult =
  | { status: "signed_in"; user: User; created: boolean }
  | { status: "needs_signup"; name: string; email: string };

/** Confirms deleting an account: its password, or a Google ID token if it has none. */
export type DeleteAccountConfirmation = { password: string } | { id_token: string };

/** What the reset-password form sends (SCRUM-63, SCRUM-69). */
export type ResetPasswordInput = {
  token: string;
  password: string;
  password_confirmation: string;
};

export type AuthStatus = "loading" | "signed-in" | "signed-out" | "error";

export type AuthContextValue = {
  status: AuthStatus;
  user: User | null;
  signIn: (email: string, password: string) => Promise<User>;
  /** Create an account and sign in (main app only; the admin portal has no register route). */
  register: (input: RegisterInput) => Promise<User>;
  /**
   * Sign in with a Google ID token (main app only). Without `signup` someone new gets
   * "needs_signup"; sending the same token with their answers creates the account.
   */
  continueWithGoogle: (idToken: string, signup?: GoogleSignupInput) => Promise<GoogleSignInResult>;
  signOut: () => Promise<void>;
  /** Delete the account, then `leave()` the page as it signs out. */
  deleteAccount: (confirmation: DeleteAccountConfirmation, leave: () => void) => Promise<void>;
  /** Email a reset link if the account exists. Resolves the same way either way. */
  requestPasswordReset: (email: string) => Promise<void>;
  /** Rejects with ApiError code "reset_link_invalid" if the link is used, expired or replaced. */
  checkResetLink: (token: string) => Promise<void>;
  /** Save a new password from a reset link. The server signs the account out everywhere. */
  resetPassword: (input: ResetPasswordInput) => Promise<void>;
  /** Re-check with the server, e.g. after "Try again". */
  refresh: () => Promise<void>;
  /** Replace the signed-in user with a newer copy the server returned (e.g. SCRUM-94). */
  setUser: (user: User) => void;
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
