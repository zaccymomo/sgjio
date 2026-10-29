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
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

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
  const { deleteAccount } = useAuth();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!password) return setError("Enter your password to confirm.");
    setDeleting(true);
    setError("");
    try {
      await deleteAccount(password);
      navigate("/sign-in", { replace: true, state: { accountDeleted: true } });
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "Something went wrong. Please try again.",
      );
    } finally {
      setDeleting(false);
    }
  }

  return (
    <AccountFormLayout title="Delete account">
      <Alert tone="error">
        This cannot be undone. Your account, profile, lesson progress and quiz attempts will be
        removed, and you will be signed out everywhere.
      </Alert>
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
    </AccountFormLayout>
  );
}
