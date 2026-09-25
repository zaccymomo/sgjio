import { useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../lib/api";
import { useAuth, type User } from "../lib/auth-context";
import { formatTime } from "../lib/format";
import { Alert } from "./Alert";
import { Button } from "./Button";
import { PasswordField } from "./PasswordField";
import { TextField } from "./TextField";

type FieldErrors = { email?: string; password?: string };

/**
 * Email + password form used by both sign-in pages. It already handles the shared
 * criteria of SCRUM-62 and SCRUM-68: empty fields highlighted (AC3), password hidden with
 * a show button (AC4), one general error message (AC2) and the "blocked, try again at"
 * message (AC5). The stories own the pages around it and their remaining criteria.
 */
export function SignInForm({
  onSuccess,
  forgotPasswordHref,
}: {
  onSuccess: (user: User) => void;
  forgotPasswordHref?: string;
}) {
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const errors: FieldErrors = {};
    if (!email.trim()) errors.email = "Enter your email.";
    if (!password) errors.password = "Enter your password.";
    setFieldErrors(errors);
    setFormError(null);
    if (errors.email) return emailRef.current?.focus();
    if (errors.password) return passwordRef.current?.focus();

    setSubmitting(true);
    try {
      onSuccess(await signIn(email, password));
    } catch (error) {
      setFormError(signInErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      {formError && <Alert tone="error">{formError}</Alert>}
      <TextField
        ref={emailRef}
        label="Email"
        type="email"
        autoComplete="email"
        inputMode="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        error={fieldErrors.email}
      />
      <PasswordField
        ref={passwordRef}
        label="Password"
        autoComplete="current-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        error={fieldErrors.password}
      />
      {forgotPasswordHref && (
        <Link
          to={forgotPasswordHref}
          className="-mt-1 self-end text-xs font-medium text-muted hover:text-ink"
        >
          Forgot password?
        </Link>
      )}
      <Button type="submit" fullWidth loading={submitting}>
        Sign in
      </Button>
    </form>
  );
}

function signInErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "Something went wrong. Please try again.";
  if (error.code === "too_many_attempts" && error.blockedUntil) {
    return `Too many failed attempts. You can try again after ${formatTime(error.blockedUntil)}.`;
  }
  return error.message;
}
