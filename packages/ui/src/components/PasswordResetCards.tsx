import { Check, KeyRound, Link2Off, LockKeyhole, MailCheck } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../lib/api";
import { useAuth } from "../lib/auth-context";
import { looksLikeEmail, passwordRuleFailures } from "../lib/validation";
import { Alert } from "./Alert";
import { AuthCard } from "./AuthCard";
import { Button } from "./Button";
import { PasswordField } from "./PasswordField";
import { PasswordRules } from "./PasswordRules";
import { Spinner } from "./Spinner";
import { TextField } from "./TextField";

/** Seconds before "Send another link" can be used again, so one click can't flood an inbox. */
const RESEND_WAIT_SECONDS = 30;

type CardChrome = {
  /** Small label next to the logo, e.g. "Admin" on the admin portal. */
  badge?: string;
  /** Under the card, e.g. "Back to sign in". */
  footer?: ReactNode;
};

/**
 * The whole "Forgot password" card for both front ends (SCRUM-63 AC1-AC3, SCRUM-69
 * AC1-AC3). The card's heading changes to "Check your email" once a link is requested.
 *
 * The confirmation is the same whether or not the email has an account (AC2), so the
 * page cannot be used to check who is registered.
 */
export function ForgotPasswordCard({
  badge,
  footer,
  subtitle = "Enter the email you signed up with and we'll send you a link to choose a new one.",
}: CardChrome & { subtitle?: string }) {
  const { requestPasswordReset } = useAuth();
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState<string>();
  const [formError, setFormError] = useState<string | null>(null);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);

  async function send(address: string) {
    setFormError(null);
    setSubmitting(true);
    try {
      await requestPasswordReset(address);
      setSentTo(address);
      return true;
    } catch (error) {
      setFormError(
        error instanceof ApiError ? error.message : "Something went wrong. Please try again.",
      );
      return false;
    } finally {
      setSubmitting(false);
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = email.trim();
    const error = !trimmed
      ? "Enter your email."
      : !looksLikeEmail(trimmed)
        ? "Enter an email address like name@example.com."
        : undefined;
    setEmailError(error);
    if (error) return emailRef.current?.focus();
    void send(trimmed);
  }

  if (sentTo) {
    return (
      <AuthCard title="Check your email" icon={MailCheck} badge={badge} footer={footer}>
        <SentConfirmation
          email={sentTo}
          error={formError}
          resending={submitting}
          onResend={() => send(sentTo)}
          onChangeEmail={() => {
            setSentTo(null);
            setFormError(null);
          }}
        />
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Forgot your password?"
      subtitle={subtitle}
      icon={KeyRound}
      badge={badge}
      footer={footer}
    >
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        {formError && <Alert tone="error">{formError}</Alert>}
        <TextField
          ref={emailRef}
          label="Email"
          type="email"
          autoComplete="email"
          inputMode="email"
          autoFocus
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={emailError}
        />
        <Button type="submit" fullWidth loading={submitting}>
          Send reset link
        </Button>
      </form>
    </AuthCard>
  );
}

function SentConfirmation({
  email,
  error,
  resending,
  onResend,
  onChangeEmail,
}: {
  email: string;
  error: string | null;
  resending: boolean;
  onResend: () => Promise<boolean>;
  onChangeEmail: () => void;
}) {
  const [wait, setWait] = useState(RESEND_WAIT_SECONDS);
  const [resent, setResent] = useState(false);

  useEffect(() => {
    if (wait <= 0) return;
    const timer = setTimeout(() => setWait((seconds) => seconds - 1), 1000);
    return () => clearTimeout(timer);
  }, [wait]);

  async function handleResend() {
    if (await onResend()) {
      setResent(true);
      setWait(RESEND_WAIT_SECONDS);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {/* AC2: worded so it is true whether or not the address has an account. */}
      <p className="text-sm text-muted">
        If <span className="font-semibold break-all text-ink">{email}</span> has an SGJio account, a
        link to reset your password is on its way.
      </p>
      <ul className="flex flex-col gap-1.5 rounded-md bg-surface p-3 text-caption text-muted">
        <li>The link works once and expires after a few minutes.</li>
        <li>Can't find it? Check your spam or junk folder.</li>
      </ul>

      {error && <Alert tone="error">{error}</Alert>}
      {resent && !error && <Alert tone="success">We've sent another link.</Alert>}

      <div className="flex flex-col gap-2">
        <Button
          type="button"
          variant="secondary"
          fullWidth
          loading={resending}
          disabled={wait > 0}
          onClick={handleResend}
        >
          {wait > 0 ? `Send another link in ${wait}s` : "Send another link"}
        </Button>
        <Button type="button" variant="ghost" fullWidth onClick={onChangeEmail}>
          Use a different email
        </Button>
      </div>
      {/* AC7 is enforced by the server; saying so here explains why older emails stop working. */}
      <p className="text-center text-2xs text-subtle">
        A new link replaces any link sent before it.
      </p>
    </div>
  );
}

type LinkState = "checking" | "valid" | "invalid";

/**
 * The whole "Choose a new password" card, where the emailed link lands (SCRUM-63 AC4-AC6,
 * SCRUM-69 AC4-AC6). The link is checked as soon as the page opens, so a used or expired
 * one is reported before anything is typed.
 */
export function ResetPasswordCard({
  token,
  onSuccess,
  forgotPasswordHref,
  badge,
  footer,
}: CardChrome & {
  token: string | null;
  /** Called once the new password is saved, e.g. to go to the sign-in page (AC5). */
  onSuccess: () => void;
  /** Where to request a new link when this one is no longer valid (AC6). */
  forgotPasswordHref: string;
}) {
  const { checkResetLink, resetPassword } = useAuth();
  const [linkState, setLinkState] = useState<LinkState>(token ? "checking" : "invalid");
  const [checkError, setCheckError] = useState<string | null>(null);

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
          setCheckError(
            error instanceof ApiError ? error.message : "Something went wrong. Please try again.",
          );
        }
      },
    );
    return () => {
      active = false;
    };
  }, [token, checkResetLink]);

  if (linkState === "invalid") {
    // AC6: say the link is dead, and make asking for a new one the obvious next step.
    return (
      <AuthCard
        title="This link is no longer valid"
        subtitle="Reset links work once, expire after a few minutes, and stop working when a newer link is sent."
        icon={Link2Off}
        badge={badge}
        footer={footer}
      >
        <LinkButton to={forgotPasswordHref}>Request a new link</LinkButton>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Choose a new password"
      subtitle={
        linkState === "valid" ? "You'll use it to sign in from now on." : "Checking your link…"
      }
      icon={LockKeyhole}
      badge={badge}
      footer={footer}
    >
      {linkState === "checking" ? (
        <CheckingLink />
      ) : (
        <NewPasswordForm
          submitLabel="Save new password"
          initialError={checkError}
          deadLinkCode="reset_link_invalid"
          onDeadLink={() => setLinkState("invalid")}
          onSubmit={async (password, confirmation) => {
            await resetPassword({
              token: token ?? "",
              password,
              password_confirmation: confirmation,
            });
            onSuccess();
          }}
        />
      )}
    </AuthCard>
  );
}

/** The spinner a card shows while its emailed link is checked. */
export function CheckingLink() {
  return (
    <div className="flex justify-center py-6 text-brand">
      <Spinner className="size-6" label="Checking your link" />
    </div>
  );
}

/** A full-width dark button that is a link, e.g. "Request a new link". */
export function LinkButton({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link
      to={to}
      className="flex h-11 items-center justify-center rounded-sm bg-ink px-4 text-sm font-semibold text-white hover:bg-ink/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
    >
      {children}
    </Link>
  );
}

type FieldErrors = { password?: string; password_confirmation?: string };

/**
 * A new password typed twice, with the rules ticked off while typing (SCRUM-61). Used by
 * the reset card, and by the admin portal's invite page (SCRUM-81).
 *
 * `onSubmit` throws an ApiError when the server refuses: one naming a field is shown on it,
 * and `deadLinkCode` (the emailed link is used or expired) calls `onDeadLink` instead.
 */
export function NewPasswordForm({
  submitLabel,
  initialError = null,
  deadLinkCode,
  onDeadLink,
  onSubmit,
}: {
  submitLabel: string;
  initialError?: string | null;
  deadLinkCode: string;
  onDeadLink: () => void;
  onSubmit: (password: string, confirmation: string) => Promise<void>;
}) {
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [triedToSubmit, setTriedToSubmit] = useState(false);
  const [formError, setFormError] = useState<string | null>(initialError);
  const [submitting, setSubmitting] = useState(false);
  const passwordRef = useRef<HTMLInputElement>(null);
  const confirmationRef = useRef<HTMLInputElement>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    setTriedToSubmit(true);

    const errors: FieldErrors = {};
    if (!password) errors.password = "Enter a new password.";
    else if (passwordRuleFailures(password).length > 0)
      errors.password = "Your password needs everything in the list below.";
    if (!confirmation) errors.password_confirmation = "Type your new password again.";
    else if (password && password !== confirmation)
      errors.password_confirmation = "The passwords do not match.";
    setFieldErrors(errors);
    if (errors.password) return passwordRef.current?.focus();
    if (errors.password_confirmation) return confirmationRef.current?.focus();

    setSubmitting(true);
    try {
      await onSubmit(password, confirmation);
    } catch (error) {
      if (!(error instanceof ApiError)) {
        setFormError("Something went wrong. Please try again.");
      } else if (error.code === deadLinkCode) {
        onDeadLink();
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

  const matches = confirmation.length > 0 && password === confirmation;

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      {formError && <Alert tone="error">{formError}</Alert>}
      <div className="flex flex-col gap-2">
        <PasswordField
          ref={passwordRef}
          label="New password"
          autoComplete="new-password"
          autoFocus
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={fieldErrors.password}
        />
        {/* The rules from SCRUM-61, ticked off while typing. */}
        <PasswordRules password={password} showUnmet={triedToSubmit} />
      </div>
      <div className="flex flex-col gap-1.5">
        <PasswordField
          ref={confirmationRef}
          label="Confirm new password"
          autoComplete="new-password"
          value={confirmation}
          onChange={(e) => setConfirmation(e.target.value)}
          error={fieldErrors.password_confirmation}
        />
        <p aria-live="polite" className="flex items-center gap-1.5 text-xs text-success">
          {matches && !fieldErrors.password_confirmation && (
            <>
              <Check className="size-3.5" aria-hidden />
              Passwords match
            </>
          )}
        </p>
      </div>
      <Button type="submit" fullWidth loading={submitting}>
        {submitLabel}
      </Button>
    </form>
  );
}
