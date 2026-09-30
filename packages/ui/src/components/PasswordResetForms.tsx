import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../lib/api";
import { useAuth } from "../lib/auth-context";
import { looksLikeEmail, passwordRuleFailures, PASSWORD_HINT } from "../lib/validation";
import { Alert } from "./Alert";
import { Button } from "./Button";
import { PasswordField } from "./PasswordField";
import { Spinner } from "./Spinner";
import { TextField } from "./TextField";

/**
 * "Forgot password" form for both front ends (SCRUM-63 AC1-AC3, SCRUM-69 AC1-AC3).
 *
 * The confirmation is the same whether or not the email has an account (AC2), so the
 * page cannot be used to check who is registered.
 */
export function ForgotPasswordForm() {
  const { requestPasswordReset } = useAuth();
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState<string>();
  const [formError, setFormError] = useState<string | null>(null);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    const error = !email.trim()
      ? "Enter your email."
      : !looksLikeEmail(email)
        ? "Enter an email address like name@example.com."
        : undefined;
    setEmailError(error);
    if (error) return emailRef.current?.focus();

    setSubmitting(true);
    try {
      await requestPasswordReset(email.trim());
      setSentTo(email.trim());
    } catch (error) {
      setFormError(
        error instanceof ApiError ? error.message : "Something went wrong. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (sentTo) {
    return (
      <div className="flex flex-col gap-4">
        <Alert tone="success">
          If <strong>{sentTo}</strong> has an SGJio account, we have sent it a link to reset your
          password. The link works once and expires soon, so use it shortly.
        </Alert>
        <p className="text-sm text-muted">
          Nothing arrived? Check your spam folder, or send another link. A new link replaces the old
          one.
        </p>
        <Button type="button" variant="secondary" fullWidth onClick={() => setSentTo(null)}>
          Send another link
        </Button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      {formError && <Alert tone="error">{formError}</Alert>}
      <p className="text-sm text-muted">
        Enter the email you signed up with and we will send you a link to choose a new password.
      </p>
      <TextField
        ref={emailRef}
        label="Email"
        type="email"
        autoComplete="email"
        inputMode="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        error={emailError}
      />
      <Button type="submit" fullWidth loading={submitting}>
        Send reset link
      </Button>
    </form>
  );
}

type LinkState = "checking" | "valid" | "invalid";
type FieldErrors = { password?: string; password_confirmation?: string };

/**
 * Where the emailed link lands (SCRUM-63 AC4-AC6, SCRUM-69 AC4-AC6). The link is checked
 * as soon as the page opens, so a used or expired one is reported before anything is typed.
 */
export function ResetPasswordForm({
  token,
  onSuccess,
  forgotPasswordHref,
}: {
  token: string | null;
  /** Called once the new password is saved, e.g. to go to the sign-in page (AC5). */
  onSuccess: () => void;
  /** Where to request a new link when this one is no longer valid (AC6). */
  forgotPasswordHref: string;
}) {
  const { checkResetLink, resetPassword } = useAuth();
  const [linkState, setLinkState] = useState<LinkState>(token ? "checking" : "invalid");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const passwordRef = useRef<HTMLInputElement>(null);
  const confirmationRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!token) return;
    let active = true;
    checkResetLink(token).then(
      () => active && setLinkState("valid"),
      (error: unknown) => {
        if (!active) return;
        if (error instanceof ApiError && error.code === "reset_link_invalid") {
          setLinkState("invalid");
        } else {
          // Could not reach the server: let them try the form, which checks again.
          setLinkState("valid");
          setFormError(
            error instanceof ApiError ? error.message : "Something went wrong. Please try again.",
          );
        }
      },
    );
    return () => {
      active = false;
    };
  }, [token, checkResetLink]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);

    const errors: FieldErrors = {};
    if (!password) errors.password = "Enter a new password.";
    else {
      const failures = passwordRuleFailures(password);
      if (failures.length > 0) errors.password = failures.join(" ");
    }
    if (!confirmation) errors.password_confirmation = "Confirm your new password.";
    else if (password && password !== confirmation)
      errors.password_confirmation = "The passwords do not match.";
    setFieldErrors(errors);
    if (errors.password) return passwordRef.current?.focus();
    if (errors.password_confirmation) return confirmationRef.current?.focus();

    setSubmitting(true);
    try {
      await resetPassword({ token: token ?? "", password, password_confirmation: confirmation });
      onSuccess();
    } catch (error) {
      if (!(error instanceof ApiError)) {
        setFormError("Something went wrong. Please try again.");
      } else if (error.code === "reset_link_invalid") {
        setLinkState("invalid");
      } else if (error.field === "password" || error.field === "password_confirmation") {
        const message = error.failures.length > 0 ? error.failures.join(" ") : error.message;
        setFieldErrors({ [error.field]: message });
      } else {
        setFormError(error.message);
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (linkState === "checking") {
    return (
      <div className="flex justify-center py-6 text-brand">
        <Spinner className="size-6" label="Checking your link" />
      </div>
    );
  }

  if (linkState === "invalid") {
    return (
      <div className="flex flex-col gap-4">
        <Alert tone="error">
          This reset link is no longer valid. Links expire soon after they are sent, work once, and
          stop working when a newer link is requested.
        </Alert>
        <Link
          to={forgotPasswordHref}
          className="flex h-11 items-center justify-center rounded-sm bg-ink px-4 text-sm font-semibold text-white hover:bg-ink/90"
        >
          Request a new link
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      {formError && <Alert tone="error">{formError}</Alert>}
      <PasswordField
        ref={passwordRef}
        label="New password"
        autoComplete="new-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        error={fieldErrors.password}
        hint={PASSWORD_HINT}
      />
      <PasswordField
        ref={confirmationRef}
        label="Confirm new password"
        autoComplete="new-password"
        value={confirmation}
        onChange={(e) => setConfirmation(e.target.value)}
        error={fieldErrors.password_confirmation}
      />
      <Button type="submit" fullWidth loading={submitting}>
        Save new password
      </Button>
    </form>
  );
}
