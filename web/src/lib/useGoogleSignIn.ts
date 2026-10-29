import { ApiError, useAuth } from "@sgjio/ui";
import { useState } from "react";

import { GoogleSignInError, googleIdToken, googleSignInAvailable } from "./google";

/** Someone new to SGJio who has been through Google's window, waiting for the sign-up step. */
export type PendingGoogleSignup = { idToken: string; name: string; email: string };

/**
 * "Continue with Google" for the sign-in and register pages (SCRUM-92).
 *
 * `onSignedIn(created)` runs once the person has a session: `created` is true for a new
 * account, which goes to profile setup. Someone new gets `signup` instead, and the page
 * shows `GoogleSignUpCard` in place of its own form.
 */
export function useGoogleSignIn(onSignedIn: (created: boolean) => void) {
  const { continueWithGoogle } = useAuth();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "info" | "error"; text: string } | null>(null);
  const [signup, setSignup] = useState<PendingGoogleSignup | null>(null);
  // Set just before leaving the page, so its "already signed in" redirect cannot race ours.
  const [finished, setFinished] = useState(false);

  async function start() {
    setBusy(true);
    setMessage(null);
    try {
      const idToken = await googleIdToken();
      const result = await continueWithGoogle(idToken);
      if (result.status === "needs_signup") {
        setSignup({ idToken, name: result.name, email: result.email });
      } else {
        setFinished(true);
        onSignedIn(result.created);
      }
    } catch (error) {
      if (error instanceof GoogleSignInError && error.reason === "cancelled") {
        setMessage({ tone: "info", text: "Google sign-in was cancelled. No account was created." });
      } else if (error instanceof GoogleSignInError || error instanceof ApiError) {
        setMessage({ tone: "error", text: error.message });
      } else {
        setMessage({ tone: "error", text: "Something went wrong. Please try again." });
      }
    } finally {
      setBusy(false);
    }
  }

  return {
    available: googleSignInAvailable,
    busy,
    message,
    signup,
    finished,
    start,
    /** Back from the sign-up step to the page, with a message if one is given. */
    cancelSignup: (text?: string) => {
      setSignup(null);
      setMessage(text ? { tone: "error", text } : null);
    },
    /** The sign-up step created the account. */
    signedUp: () => {
      setFinished(true);
      onSignedIn(true);
    },
  };
}
