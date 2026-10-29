import { cn, type UserType } from "@sgjio/ui";
import type { RefObject } from "react";
import { Link } from "react-router-dom";

/** Matches NOTICE_VERSION in api/app/privacy.py. */
export const PRIVACY_NOTICE_VERSION = "2026-10-22";

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

/**
 * Newcomer or Singaporean, as two selectable cards. Native radios do the keyboard and
 * screen-reader work; the cards are the label around each one. Asked when registering
 * with a password (SCRUM-61) and when signing up with Google (SCRUM-92).
 */
export function UserTypeChoice({
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

/** "I agree to the privacy notice", required before any account is created (SCRUM-79). */
export function PrivacyConsent({
  checked,
  onChange,
  error,
  inputRef,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  error: string | null;
  inputRef: RefObject<HTMLInputElement | null>;
}) {
  return (
    <div className={cn("rounded-sm border p-3", error ? "border-danger" : "border-line")}>
      <label className="flex items-start gap-2 text-sm text-ink">
        <input
          ref={inputRef}
          type="checkbox"
          checked={checked}
          onChange={(event) => onChange(event.target.checked)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? "privacy-consent-error" : undefined}
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
      {error && (
        <p id="privacy-consent-error" className="mt-2 text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
