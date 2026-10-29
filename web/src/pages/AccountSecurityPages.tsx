import {
  Alert,
  ApiError,
  Button,
  PASSWORD_HINT,
  PasswordField,
  apiFetch,
  passwordRuleFailures,
  useAuth,
} from "@sgjio/ui";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { GoogleLogo } from "../components/GoogleSignIn";
import { GoogleSignInError, googleIdToken, preloadGoogle } from "../lib/google";

function AccountFormLayout({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mx-auto w-full max-w-xl space-y-4">
      <Link to="/settings" className="text-sm text-brand underline">
        Back to Settings
      </Link>
      <h1 className="text-[22px] font-bold text-ink">{title}</h1>
      {children}
    </div>
  );
}

export function ChangePasswordPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [generalError, setGeneralError] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const nextErrors: Record<string, string> = {};
    if (!current) nextErrors.current_password = "Enter your current password.";
    if (!password) nextErrors.password = "Enter a new password.";
    else {
      const failures = passwordRuleFailures(password);
      if (failures.length) nextErrors.password = failures.join(" ");
    }
    if (!confirmation) nextErrors.password_confirmation = "Confirm your new password.";
    else if (password !== confirmation)
      nextErrors.password_confirmation = "The passwords do not match.";
    setErrors(nextErrors);
    setGeneralError("");
    if (Object.keys(nextErrors).length) return;
    setSaving(true);
    try {
      await apiFetch<void>("/api/auth/change-password", {
        method: "POST",
        body: { current_password: current, password, password_confirmation: confirmation },
      });
      navigate("/settings", { replace: true, state: { passwordChanged: true } });
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.code === "too_many_attempts") {
          setGeneralError(
            `${error.message} Try again after ${error.blockedUntil?.toLocaleTimeString() ?? "the block expires"}.`,
          );
        } else if (error.field) {
          setErrors({
            [error.field]: error.failures.length ? error.failures.join(" ") : error.message,
          });
        } else setGeneralError(error.message);
      } else setGeneralError("Something went wrong. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  // Accounts created with Google have no password to change (SCRUM-92).
  if (user && !user.has_password) return <Navigate to="/settings" replace />;

  return (
    <AccountFormLayout title="Change password">
      <p className="text-sm text-muted">
        You will stay signed in here. Other sessions and earlier password-reset links will stop
        working.
      </p>
      {generalError && <Alert tone="error">{generalError}</Alert>}
      <form onSubmit={submit} className="space-y-4">
        <PasswordField
          label="Current password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          error={errors.current_password}
        />
        <PasswordField
          label="New password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
          hint={PASSWORD_HINT}
        />
        <PasswordField
          label="Confirm new password"
          autoComplete="new-password"
          value={confirmation}
          onChange={(e) => setConfirmation(e.target.value)}
          error={errors.password_confirmation}
        />
        <Button type="submit" loading={saving}>
          Save new password
        </Button>
      </form>
    </AccountFormLayout>
  );
}

export function DeleteAccountPage() {
  const { user } = useAuth();

  return (
    <AccountFormLayout title="Delete account">
      <Alert tone="error">
        This cannot be undone. Your account, profile, lesson progress and quiz attempts will be
        removed, and you will be signed out everywhere.
      </Alert>
      {user && !user.has_password ? <ConfirmWithGoogle /> : <ConfirmWithPassword />}
    </AccountFormLayout>
  );
}

/** After deleting, the sign-in page says the account is gone. */
function useLeaveDeleted() {
  const navigate = useNavigate();
  return () => navigate("/sign-in", { replace: true, state: { accountDeleted: true } });
}

function ConfirmWithPassword() {
  const { deleteAccount } = useAuth();
  const leaveDeleted = useLeaveDeleted();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!password) return setError("Enter your password to confirm.");
    setDeleting(true);
    setError("");
    try {
      await deleteAccount({ password }, leaveDeleted);
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "Something went wrong. Please try again.",
      );
    } finally {
      setDeleting(false);
    }
  }

  return (
    <>
      {error && <Alert tone="error">{error}</Alert>}
      <form onSubmit={submit} className="space-y-4">
        <PasswordField
          label="Enter your password to confirm"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={error && !password ? error : undefined}
        />
        <Button type="submit" loading={deleting}>
          Permanently delete my account
        </Button>
      </form>
    </>
  );
}

/** An account created with Google has no password: signing in with Google again confirms. */
function ConfirmWithGoogle() {
  const { user, deleteAccount } = useAuth();
  const leaveDeleted = useLeaveDeleted();
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    void preloadGoogle().catch(() => undefined);
  }, []);

  async function confirm() {
    setDeleting(true);
    setError("");
    try {
      const idToken = await googleIdToken();
      await deleteAccount({ id_token: idToken }, leaveDeleted);
    } catch (cause) {
      if (cause instanceof GoogleSignInError && cause.reason === "cancelled") {
        setError("You didn't confirm with Google, so your account was not deleted.");
      } else {
        setError(
          cause instanceof GoogleSignInError || cause instanceof ApiError
            ? cause.message
            : "Something went wrong. Please try again.",
        );
      }
    } finally {
      setDeleting(false);
    }
  }

  return (
    <>
      {error && <Alert tone="error">{error}</Alert>}
      {/* Laid out like the password form: what confirms it, then the same button. */}
      <div className="space-y-4">
        <div>
          <p className="text-xs font-semibold text-ink">Confirm with Google</p>
          <div className="mt-1.5 flex items-start gap-3 rounded-sm border border-line bg-surface p-3">
            <GoogleLogo className="mt-0.5" />
            <p className="text-sm text-muted">
              Google will open and ask you to choose an account. Choose{" "}
              <span className="font-semibold break-words text-ink">{user?.email}</span>, the one you
              sign in with. Your account is deleted as soon as you do.
            </p>
          </div>
        </div>
        <Button onClick={() => void confirm()} loading={deleting}>
          Permanently delete my account
        </Button>
      </div>
    </>
  );
}
