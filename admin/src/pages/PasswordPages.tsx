import {
  Alert,
  ApiError,
  AuthCard,
  Button,
  PASSWORD_HINT,
  PasswordField,
  TextField,
  apiFetch,
  passwordRuleFailures,
} from "@sgjio/ui";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

const REQUEST_PATH = "/api/admin/auth/forgot-password";
const VALIDATE_PATH = "/api/admin/auth/reset-password/check";
const CONFIRM_PATH = "/api/admin/auth/reset-password";

const backToSignIn = (
  <Link to="/sign-in" className="font-semibold text-brand hover:underline">
    Back to sign in
  </Link>
);

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState<string | undefined>();
  const [formError, setFormError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!email.trim()) {
      setEmailError("Enter your email.");
      emailRef.current?.focus();
      return;
    }

    setEmailError(undefined);
    setFormError(null);
    setSubmitting(true);
    try {
      await apiFetch<void>(REQUEST_PATH, { method: "POST", body: { email } });
      setSent(true);
    } catch {
      setFormError("We couldn't process your request. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthCard
      title="Forgot your password?"
      subtitle="Enter your email and we'll send a reset link if it belongs to an administrator account."
      badge="Admin"
      footer={backToSignIn}
    >
      {sent ? (
        <Alert tone="success">
          If an administrator account uses that email, we have sent a password reset link. It is valid
          for 5 minutes.
        </Alert>
      ) : (
        <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
          {formError && <Alert tone="error">{formError}</Alert>}
          <TextField
            ref={emailRef}
            label="Email"
            type="email"
            autoComplete="email"
            inputMode="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            error={emailError}
          />
          <Button type="submit" fullWidth loading={submitting}>
            Send reset link
          </Button>
        </form>
      )}
    </AuthCard>
  );
}

/** Where an emailed admin reset link lands: /reset-password?token=... (SCRUM-69 AC4-7). */
export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token");
  const [checking, setChecking] = useState(true);
  const [valid, setValid] = useState(false);
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [complete, setComplete] = useState(false);
  const passwordRef = useRef<HTMLInputElement>(null);
  const confirmationRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;
    if (!token) return;
    void apiFetch<void>(VALIDATE_PATH, { method: "POST", body: { token } })
      .then(() => {
        if (active) setValid(true);
      })
      .catch(() => {
        // A link that cannot be checked is not safe to use; invite a fresh request instead.
        if (active) setValid(false);
      })
      .finally(() => {
        if (active) setChecking(false);
      });
    return () => {
      active = false;
    };
  }, [token]);

  useEffect(() => {
    if (!complete) return;
    const timeout = window.setTimeout(() => navigate("/sign-in", { replace: true }), 2000);
    return () => window.clearTimeout(timeout);
  }, [complete, navigate]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!token) return;

    const errors: Record<string, string> = {};
    const passwordFailures = passwordRuleFailures(password);
    if (!password) errors.password = "Enter a new password.";
    else if (passwordFailures.length) errors.password = passwordFailures.join(" ");
    if (!passwordConfirmation) errors.password_confirmation = "Confirm your new password.";
    else if (password !== passwordConfirmation)
      errors.password_confirmation = "The passwords do not match.";
    setFieldErrors(errors);
    setFormError(null);
    if (errors.password) return passwordRef.current?.focus();
    if (errors.password_confirmation) return confirmationRef.current?.focus();

    setSubmitting(true);
    try {
      await apiFetch<void>(CONFIRM_PATH, {
        method: "POST",
        body: { token, password, password_confirmation: passwordConfirmation },
      });
      setComplete(true);
    } catch (error) {
      if (error instanceof ApiError && error.code === "reset_link_invalid") {
        setValid(false);
      } else if (error instanceof ApiError && error.field) {
        setFieldErrors({ [error.field]: error.message });
      } else {
        setFormError("We couldn't reset your password. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (token && checking) {
    return (
      <AuthCard title="Choose a new password" badge="Admin" footer={backToSignIn}>
        <p className="text-sm text-muted">Checking your reset link…</p>
      </AuthCard>
    );
  }

  if (!valid) {
    return (
      <AuthCard title="Reset link unavailable" badge="Admin" footer={backToSignIn}>
        <Alert tone="error">This password reset link is no longer valid. Request a new one.</Alert>
        <Link
          to="/forgot-password"
          className="mt-4 inline-block text-sm font-semibold text-brand hover:underline"
        >
          Request a new reset link
        </Link>
      </AuthCard>
    );
  }

  if (complete) {
    return (
      <AuthCard title="Password reset" badge="Admin" footer={backToSignIn}>
        <Alert tone="success">Your password has been reset. Taking you to sign in…</Alert>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Choose a new password"
      subtitle="Use at least 8 characters, including a letter and a number."
      badge="Admin"
      footer={backToSignIn}
    >
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        {formError && <Alert tone="error">{formError}</Alert>}
        <PasswordField
          ref={passwordRef}
          label="New password"
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={fieldErrors.password}
          hint={PASSWORD_HINT}
        />
        <PasswordField
          ref={confirmationRef}
          label="Confirm new password"
          autoComplete="new-password"
          value={passwordConfirmation}
          onChange={(event) => setPasswordConfirmation(event.target.value)}
          error={fieldErrors.password_confirmation}
        />
        <Button type="submit" fullWidth loading={submitting}>
          Reset password
        </Button>
      </form>
    </AuthCard>
  );
}
