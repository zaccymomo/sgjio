/**
 * Google's sign-in window, through Firebase Authentication (SCRUM-92).
 *
 * Firebase is only used to open the window and hand back Google's ID token. The token goes
 * to our API, which checks it and starts an ordinary SGJio session; Firebase keeps nothing
 * (in-memory persistence, and it is signed out straight away).
 *
 * Needs the VITE_FIREBASE_* values in web/.env (README, "Sign in with Google"). Without
 * them `googleSignInAvailable` is false and the pages show no Google button.
 */
import type { Auth } from "firebase/auth";

const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY as string | undefined,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN as string | undefined,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID as string | undefined,
  appId: import.meta.env.VITE_FIREBASE_APP_ID as string | undefined,
};

export const googleSignInAvailable = Boolean(
  config.apiKey && config.authDomain && config.projectId,
);

/** Why no token came back, worded for the page to show. */
export class GoogleSignInError extends Error {
  readonly reason: "cancelled" | "blocked" | "failed";

  constructor(reason: GoogleSignInError["reason"], message: string) {
    super(message);
    this.name = "GoogleSignInError";
    this.reason = reason;
  }
}

let loading: Promise<{ auth: Auth; sdk: typeof import("firebase/auth") }> | null = null;

/**
 * Load Firebase, once. Called when a Google button first shows, so that selecting it can
 * open the window at once: browsers block windows that open long after the click.
 */
export function preloadGoogle() {
  if (!googleSignInAvailable) return Promise.reject(new Error("Google sign-in is not set up"));
  loading ??= (async () => {
    const [{ initializeApp }, sdk] = await Promise.all([
      import("firebase/app"),
      import("firebase/auth"),
    ]);
    const app = initializeApp(config);
    const auth = sdk.initializeAuth(app, {
      persistence: sdk.inMemoryPersistence,
      popupRedirectResolver: sdk.browserPopupRedirectResolver,
    });
    return { auth, sdk };
  })();
  return loading;
}

/** Open Google's sign-in window and return the ID token for our API. */
export async function googleIdToken(): Promise<string> {
  let firebase;
  try {
    firebase = await preloadGoogle();
  } catch {
    throw new GoogleSignInError(
      "failed",
      "Google sign-in couldn't load. Check your connection and try again.",
    );
  }
  const { auth, sdk } = firebase;
  const provider = new sdk.GoogleAuthProvider();
  // Always offer the choice of account, so nobody is signed in with the wrong one.
  provider.setCustomParameters({ prompt: "select_account" });

  try {
    const result = await sdk.signInWithPopup(auth, provider);
    return await result.user.getIdToken();
  } catch (error) {
    throw toSignInError(error);
  } finally {
    await sdk.signOut(auth).catch(() => undefined);
  }
}

function toSignInError(error: unknown): GoogleSignInError {
  const code = (error as { code?: string } | null)?.code ?? "";
  if (
    code === "auth/popup-closed-by-user" ||
    code === "auth/cancelled-popup-request" ||
    code === "auth/user-cancelled"
  ) {
    return new GoogleSignInError("cancelled", "Google sign-in was cancelled.");
  }
  if (code === "auth/popup-blocked") {
    return new GoogleSignInError(
      "blocked",
      "Your browser blocked Google's sign-in window. Allow pop-ups for this site and try again.",
    );
  }
  if (code === "auth/network-request-failed") {
    return new GoogleSignInError(
      "failed",
      "We couldn't reach Google. Check your connection and try again.",
    );
  }
  return new GoogleSignInError("failed", "Google sign-in didn't work. Please try again.");
}
