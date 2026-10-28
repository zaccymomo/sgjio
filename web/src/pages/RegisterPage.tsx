import {
  Alert,
  ApiError,
  AuthCard,
  Button,
  PASSWORD_HINT,
  PasswordField,
  TextField,
  cn,
  looksLikeEmail,
  passwordRuleFailures,
  useAuth,
  type UserType,
} from "@sgjio/ui";
import { useRef, useState, type FormEvent, type RefObject } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

const PRIVACY_NOTICE_VERSION = "2026-10-22";

/** The two user types, self-reported (SCRUM-61 AC1). */
const USER_TYPES: Array<{ value: UserType; label: string; description: string }> = [
  {
    value: "newcomer",
    label: "Newcomer",
    description: "New to Singapore and learning how things work here.",
  },
  {
    value: "singaporean",
    label: "Singaporean",
    description: "Living here already and happy to share local know-how.",
  },
];

type FieldName = "name" | "email" | "password" | "password_confirmation";
type FieldErrors = Partial<Record<FieldName, string>>;

/** The order fields appear in, which is the order errors are focused in. */
const FIELD_ORDER: FieldName[] = ["name", "email", "password", "password_confirmation"];

/**
 * Registration (SCRUM-61). Everything the reader can be told without asking the server is
 * checked here first; the API re-checks all of it and owns the rules the browser cannot
 * know, above all whether the email is already registered.
 */
export function RegisterPage() {
  const { status, register } = useAuth();
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [userType, setUserType] = useState<UserType | null>(null);
  const [privacyConsent, setPrivacyConsent] = useState(false);
  const [privacyError, setPrivacyError] = useState<string | null>(null);

  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [userTypeError, setUserTypeError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [emailTaken, setEmailTaken] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const nameRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const confirmationRef = useRef<HTMLInputElement>(null);
  const userTypeRef = useRef<HTMLInputElement>(null);
  const privacyRef = useRef<HTMLInputElement>(null);

  // Someone who is already signed in has no use for this page. `registered` keeps the
  // redirect from racing this page's own move to profile setup (AC8).
  const [registered, setRegistered] = useState(false);
  if (status === "signed-in" && !registered) return <Navigate to="/" replace />;

  /** Highlighted fields are read top to bottom, so focus the first one that has a message. */
  function focusFirstError(errors: FieldErrors) {
    const fields: Array<[FieldName, RefObject<HTMLInputElement | null>]> = [
      ["name", nameRef],
      ["email", emailRef],
      ["password", passwordRef],
      ["password_confirmation", confirmationRef],
    ];
    const first = fields.find(([field]) => errors[field]);
    first?.[1].current?.focus();
    return first !== undefined;
  }

  function validate(): { errors: FieldErrors; missingUserType: boolean } {
    const errors: FieldErrors = {};

    if (!name.trim()) errors.name = "Enter your name."; // AC6
    if (!email.trim())
      errors.email = "Enter your email."; // AC6
    else if (!looksLikeEmail(email)) errors.email = "Enter an email address like name@example.com."; // AC3

    if (!password) {
      errors.password = "Enter a password."; // AC6
    } else {
      const failures = passwordRuleFailures(password);
      if (failures.length > 0) errors.password = failures.join(" "); // AC4
    }

    if (!passwordConfirmation) {
      errors.password_confirmation = "Confirm your password."; // AC6
    } else if (password && password !== passwordConfirmation) {
      errors.password_confirmation = "The passwords do not match."; // AC5
    }

    return { errors, missingUserType: userType === null };
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    setEmailTaken(false);

    const { errors, missingUserType } = validate();
    setFieldErrors(errors);
    setUserTypeError(missingUserType ? "Select Newcomer or Singaporean." : null);
    setPrivacyError(
      privacyConsent ? null : "Agree to the privacy notice before creating an account.",
    );

    // Nothing is sent while a field is wrong, and the first one is focused (AC6).
    if (focusFirstError(errors)) return;
    if (missingUserType || userType === null) return userTypeRef.current?.focus();
    if (!privacyConsent) return privacyRef.current?.focus();

    setSubmitting(true);
    try {
      await register({
        name: name.trim(),
        email: email.trim(),
        password,
        password_confirmation: passwordConfirmation,
        user_type: userType,
        privacy_consent: true,
        privacy_notice_version: PRIVACY_NOTICE_VERSION,
      });
      setRegistered(true);
      // First sign-in goes to profile setup (AC8), which SCRUM-14 builds.
      navigate("/profile-setup", { replace: true });
    } catch (error) {
      showApiError(error);
    } finally {
      setSubmitting(false);
    }
  }

  /** Put the API's answer on the field it blames, or in the message box above the form. */
  function showApiError(error: unknown) {
    if (!(error instanceof ApiError)) {
      setFormError("Something went wrong. Please try again.");
      return;
    }

    if (error.code === "email_taken") {
      // AC2: say the email is in use, and offer the sign-in page instead.
      setEmailTaken(true);
      setFieldErrors({ email: error.message });
      emailRef.current?.focus();
      return;
    }

    // Our own checks name one field; FastAPI's own validation names several.
    const named: FieldErrors = {};
    for (const [field, message] of Object.entries(error.fieldErrors)) {
      if (FIELD_ORDER.includes(field as FieldName)) named[field as FieldName] = message;
    }
    if (error.field && FIELD_ORDER.includes(error.field as FieldName)) {
      // A broken password lists every rule it fails (AC4).
      named[error.field as FieldName] =
        error.failures.length > 0 ? error.failures.join(" ") : error.message;
    }

    if (Object.keys(named).length > 0) {
      setFieldErrors(named);
      focusFirstError(named);
      return;
    }
    if (error.fieldErrors.user_type) {
      setUserTypeError("Select Newcomer or Singaporean.");
      return;
    }
    if (error.field === "privacy_consent" || error.fieldErrors.privacy_consent) {
      setPrivacyError(error.message);
      setPrivacyConsent(false);
      privacyRef.current?.focus();
      return;
    }
    setFormError(error.message);
  }

  return (
    <AuthCard
      title="Create an account"
      subtitle="A few details, and your progress is saved to you."
      footer={
        <>
          Already have an account?{" "}
          <Link to="/sign-in" className="font-semibold text-brand hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        {emailTaken && (
          <Alert tone="error">
            That email is already registered.{" "}
            <Link to="/sign-in" className="font-semibold underline">
              Sign in instead
            </Link>
            .
          </Alert>
        )}
        {formError && <Alert tone="error">{formError}</Alert>}

        <TextField
          ref={nameRef}
          label="Name"
          autoComplete="name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          error={fieldErrors.name}
        />
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
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={fieldErrors.password}
          hint={PASSWORD_HINT}
        />
        <PasswordField
          ref={confirmationRef}
          label="Confirm password"
          autoComplete="new-password"
          value={passwordConfirmation}
          onChange={(e) => setPasswordConfirmation(e.target.value)}
          error={fieldErrors.password_confirmation}
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

        <div
          className={cn("rounded-sm border p-3", privacyError ? "border-danger" : "border-line")}
        >
          <label className="flex items-start gap-2 text-sm text-ink">
            <input
              ref={privacyRef}
              type="checkbox"
              checked={privacyConsent}
              onChange={(event) => {
                setPrivacyConsent(event.target.checked);
                setPrivacyError(null);
              }}
              aria-invalid={privacyError ? true : undefined}
              aria-describedby={privacyError ? "privacy-consent-error" : undefined}
              className="mt-0.5 size-4 accent-brand"
            />
            <span>
              I agree to the{" "}
              <Link
                to="/privacy"
                target="_blank"
                rel="noopener noreferrer"
                className="font-semibold text-brand underline"
              >
                privacy notice (opens in a new tab)
              </Link>
              .
            </span>
          </label>
          {privacyError && (
            <p id="privacy-consent-error" className="mt-2 text-xs text-danger">
              {privacyError}
            </p>
          )}
        </div>

        <Button type="submit" fullWidth loading={submitting}>
          Create account
        </Button>
      </form>
    </AuthCard>
  );
}

/**
 * Newcomer or Singaporean, as two selectable cards. Native radios do the keyboard and
 * screen-reader work; the cards are the label around each one.
 */
function UserTypeChoice({
  value,
  onChange,
  error,
  firstOptionRef,
}: {
  value: UserType | null;
  onChange: (value: UserType) => void;
  error: string | null;
  firstOptionRef: RefObject<HTMLInputElement | null>;
}) {
  return (
    <fieldset className="flex flex-col gap-1.5">
      <legend className="mb-1.5 text-xs font-semibold text-ink">I am a</legend>
      <div
        className="flex flex-col gap-2"
        aria-describedby={error ? "user-type-message" : undefined}
      >
        {USER_TYPES.map((option, index) => {
          const selected = value === option.value;
          return (
            <label
              key={option.value}
              className={cn(
                "flex cursor-pointer items-start gap-3 rounded-sm border bg-white p-3",
                "transition-colors focus-within:ring-2",
                selected
                  ? "border-brand ring-2 ring-brand/20"
                  : error
                    ? "border-danger focus-within:ring-danger/20"
                    : "border-line hover:bg-surface focus-within:border-ink focus-within:ring-ink/10",
              )}
            >
              <input
                ref={index === 0 ? firstOptionRef : undefined}
                type="radio"
                name="user_type"
                value={option.value}
                checked={selected}
                onChange={() => onChange(option.value)}
                aria-invalid={error ? true : undefined}
                className="mt-0.5 size-4 shrink-0 accent-brand"
              />
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-ink">{option.label}</span>
                <span className="block text-caption text-muted">{option.description}</span>
              </span>
            </label>
          );
        })}
      </div>
      {error && (
        <p id="user-type-message" className="text-xs text-danger">
          {error}
        </p>
      )}
    </fieldset>
  );
}
