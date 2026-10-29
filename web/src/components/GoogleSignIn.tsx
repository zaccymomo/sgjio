import {
  Alert,
  ApiError,
  AuthCard,
  Button,
  TextField,
  cn,
  useAuth,
  type UserType,
} from "@sgjio/ui";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { preloadGoogle } from "../lib/google";
import type { PendingGoogleSignup, useGoogleSignIn } from "../lib/useGoogleSignIn";
import { PRIVACY_NOTICE_VERSION, PrivacyConsent, UserTypeChoice } from "./AccountChoices";

type GoogleSignIn = ReturnType<typeof useGoogleSignIn>;

/** The Google button and an "or" line, above a page's email form. Nothing if not set up. */
export function GoogleOption({ google }: { google: GoogleSignIn }) {
  // Load Firebase as soon as the button shows, so selecting it opens Google's window at once.
  useEffect(() => {
    if (google.available) void preloadGoogle().catch(() => undefined);
  }, [google.available]);

  if (!google.available) return null;
  return (
    <div className="mb-5 flex flex-col gap-4">
      {google.message && <Alert tone={google.message.tone}>{google.message.text}</Alert>}
      <GoogleButton onClick={() => void google.start()} loading={google.busy} />
      <div className="flex items-center gap-3 text-caption text-subtle" aria-hidden>
        <span className="h-px flex-1 bg-line" />
        or use your email
        <span className="h-px flex-1 bg-line" />
      </div>
    </div>
  );
}

export function GoogleButton({
  onClick,
  loading,
  children = "Continue with Google",
}: {
  onClick: () => void;
  loading?: boolean;
  children?: string;
}) {
  return (
    <Button variant="secondary" fullWidth onClick={onClick} loading={loading}>
      {!loading && <GoogleLogo />}
      {children}
    </Button>
  );
}

/** Google's "G", in Google's colours, as its brand guidelines ask for on sign-in buttons. */
export function GoogleLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={cn("size-4.5 shrink-0", className)} aria-hidden>
      <path
        fill="#FFC107"
        d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z"
      />
      <path
        fill="#FF3D00"
        d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"
      />
      <path
        fill="#4CAF50"
        d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-7.9l-6.5 5C9.5 39.6 16.2 44 24 44z"
      />
      <path
        fill="#1976D2"
        d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z"
      />
    </svg>
  );
}

/**
 * The one step someone new answers after Google (SCRUM-92): their name as Google gave it
 * (they can change it), Newcomer or Singaporean, and the privacy notice. Their email is
 * Google's, so it is shown but not asked for.
 */
export function GoogleSignUpCard({
  signup,
  onCancel,
  onSignedUp,
}: {
  signup: PendingGoogleSignup;
  onCancel: (message?: string) => void;
  onSignedUp: () => void;
}) {
  const { continueWithGoogle } = useAuth();
  const [name, setName] = useState(signup.name);
  const [userType, setUserType] = useState<UserType | null>(null);
  const [privacyConsent, setPrivacyConsent] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);
  const [userTypeError, setUserTypeError] = useState<string | null>(null);
  const [privacyError, setPrivacyError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const nameRef = useRef<HTMLInputElement>(null);
  const userTypeRef = useRef<HTMLInputElement>(null);
  const privacyRef = useRef<HTMLInputElement>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    const missingName = !name.trim();
    setNameError(missingName ? "Enter your name." : null);
    setUserTypeError(userType ? null : "Select Newcomer or Singaporean.");
    setPrivacyError(
      privacyConsent ? null : "Agree to the privacy notice before creating an account.",
    );
    if (missingName) return nameRef.current?.focus();
    if (!userType) return userTypeRef.current?.focus();
    if (!privacyConsent) return privacyRef.current?.focus();

    setSubmitting(true);
    try {
      await continueWithGoogle(signup.idToken, {
        name: name.trim(),
        user_type: userType,
        privacy_consent: true,
        privacy_notice_version: PRIVACY_NOTICE_VERSION,
      });
      onSignedUp();
    } catch (error) {
      if (!(error instanceof ApiError)) {
        setFormError("Something went wrong. Please try again.");
      } else if (error.code === "google_token_invalid") {
        // Google's token lasts an hour; after that they go through Google again.
        onCancel("Your Google sign-in has expired. Select Continue with Google again.");
      } else if (error.field === "privacy_consent") {
        setPrivacyConsent(false);
        setPrivacyError(error.message);
        privacyRef.current?.focus();
      } else {
        setFormError(error.message);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthCard
      title="Finish creating your account"
      subtitle={
        <>
          You're signing up with Google as{" "}
          <span className="font-semibold break-words text-ink">{signup.email}</span>.
        </>
      }
      footer={
        <button
          type="button"
          onClick={() => onCancel()}
          className="font-semibold text-brand hover:underline"
        >
          Cancel and go back
        </button>
      }
    >
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        {formError && <Alert tone="error">{formError}</Alert>}
        <TextField
          ref={nameRef}
          label="Name"
          autoComplete="name"
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            setNameError(null);
          }}
          error={nameError ?? undefined}
          hint="From your Google account. Change it if you like."
        />
        <UserTypeChoice
          value={userType}
          onChange={(next) => {
            setUserType(next);
            setUserTypeError(null);
          }}
          error={userTypeError}
          firstOptionRef={userTypeRef}
        />
        <PrivacyConsent
          checked={privacyConsent}
          onChange={(checked) => {
            setPrivacyConsent(checked);
            setPrivacyError(null);
          }}
          error={privacyError}
          inputRef={privacyRef}
        />
        <Button type="submit" fullWidth loading={submitting}>
          Create account
        </Button>
      </form>
    </AuthCard>
  );
}
