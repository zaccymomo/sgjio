import { Alert, ApiError, Button, cn } from "@sgjio/ui";
import { Check } from "lucide-react";
import { useId, useRef, useState, type FormEvent, type ReactNode, type RefObject } from "react";

import { saveProfile, type Profile, type ProfileOptions } from "../lib/profile";

type FieldName = "interests" | "languages" | "neighbourhood";
type FieldErrors = Partial<Record<FieldName, string>>;

const FIELD_ORDER: FieldName[] = ["interests", "languages", "neighbourhood"];

/**
 * Interests, languages and neighbourhood (SCRUM-14). Used for onboarding and for editing
 * from Settings, so there is one place that saves a profile (SCRUM-41 note).
 */
export function ProfileForm({
  initial,
  options,
  submitLabel,
  onSaved,
  secondaryAction,
}: {
  initial: Profile;
  options: ProfileOptions;
  submitLabel: string;
  onSaved: (profile: Profile) => void;
  /** e.g. "Skip for now" or "Cancel", shown beside the submit button. */
  secondaryAction?: ReactNode;
}) {
  const [interests, setInterests] = useState(initial.interests);
  const [languages, setLanguages] = useState(initial.languages);
  const [neighbourhood, setNeighbourhood] = useState(initial.neighbourhood ?? "");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const interestsRef = useRef<HTMLButtonElement>(null);
  const languagesRef = useRef<HTMLButtonElement>(null);
  const neighbourhoodRef = useRef<HTMLSelectElement>(null);

  /** Highlight the fields and focus the first one, top to bottom. */
  function showErrors(next: FieldErrors) {
    setErrors(next);
    const first = FIELD_ORDER.find((field) => next[field]);
    const refs = {
      interests: interestsRef,
      languages: languagesRef,
      neighbourhood: neighbourhoodRef,
    };
    if (first) refs[first].current?.focus();
    return first !== undefined;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);

    // AC2: every incomplete field is highlighted and nothing is saved.
    const missing: FieldErrors = {};
    if (interests.length === 0) missing.interests = "Select at least one interest.";
    if (languages.length === 0) missing.languages = "Select at least one language you speak.";
    if (!neighbourhood) missing.neighbourhood = "Select your neighbourhood.";
    if (showErrors(missing)) return;

    setSubmitting(true);
    try {
      onSaved(await saveProfile({ interests, languages, neighbourhood }));
    } catch (error) {
      if (!(error instanceof ApiError)) {
        setFormError("Something went wrong. Please try again.");
        return;
      }
      const named: FieldErrors = {};
      for (const field of FIELD_ORDER) {
        if (error.fieldErrors[field]) named[field] = error.fieldErrors[field];
      }
      if (!showErrors(named)) setFormError(error.message);
    } finally {
      setSubmitting(false);
    }
  }

  function toggle(list: string[], value: string) {
    return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-6">
      {formError && <Alert tone="error">{formError}</Alert>}

      <ChoiceGroup
        legend="Interests"
        hint="Select everything you enjoy. We use this to suggest lessons and buddies."
        choices={options.interests}
        selected={interests}
        onToggle={(value) => {
          setInterests((current) => toggle(current, value));
          setErrors((current) => ({ ...current, interests: undefined }));
        }}
        error={errors.interests}
        firstRef={interestsRef}
      />

      <ChoiceGroup
        legend="Languages you speak"
        choices={options.languages}
        selected={languages}
        onToggle={(value) => {
          setLanguages((current) => toggle(current, value));
          setErrors((current) => ({ ...current, languages: undefined }));
        }}
        error={errors.languages}
        firstRef={languagesRef}
      />

      <NeighbourhoodSelect
        value={neighbourhood}
        choices={options.neighbourhoods}
        onChange={(value) => {
          setNeighbourhood(value);
          setErrors((current) => ({ ...current, neighbourhood: undefined }));
        }}
        error={errors.neighbourhood}
        selectRef={neighbourhoodRef}
      />

      <div className="flex flex-col gap-2 sm:flex-row-reverse sm:justify-start">
        <Button type="submit" loading={submitting}>
          {submitLabel}
        </Button>
        {secondaryAction}
      </div>
    </form>
  );
}

/** A set of on/off chips. Each chip is a button with aria-pressed. */
function ChoiceGroup({
  legend,
  hint,
  choices,
  selected,
  onToggle,
  error,
  firstRef,
}: {
  legend: string;
  hint?: string;
  choices: string[];
  selected: string[];
  onToggle: (value: string) => void;
  error?: string;
  firstRef: RefObject<HTMLButtonElement | null>;
}) {
  const messageId = useId();
  const message = error ?? hint;

  return (
    <fieldset aria-describedby={message ? messageId : undefined}>
      <legend className="mb-1.5 text-xs font-semibold text-ink">
        {legend}
        {selected.length > 0 && (
          <span className="ml-1.5 font-normal text-muted">{selected.length} selected</span>
        )}
      </legend>
      <div
        className={cn(
          "flex flex-wrap gap-2 rounded-md",
          error && "border border-danger bg-danger-soft/40 p-2",
        )}
      >
        {choices.map((choice, index) => {
          const on = selected.includes(choice);
          return (
            <button
              key={choice}
              ref={index === 0 ? firstRef : undefined}
              type="button"
              aria-pressed={on}
              onClick={() => onToggle(choice)}
              className={cn(
                "inline-flex h-9 items-center gap-1.5 rounded-full border px-3 text-sm transition-colors",
                "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink",
                on
                  ? "border-ink bg-ink font-medium text-white"
                  : "border-line bg-white text-ink hover:bg-surface",
              )}
            >
              {on && <Check className="size-3.5" aria-hidden />}
              {choice}
            </button>
          );
        })}
      </div>
      {message && (
        <p id={messageId} className={cn("mt-1.5 text-xs", error ? "text-danger" : "text-muted")}>
          {message}
        </p>
      )}
    </fieldset>
  );
}

function NeighbourhoodSelect({
  value,
  choices,
  onChange,
  error,
  selectRef,
}: {
  value: string;
  choices: string[];
  onChange: (value: string) => void;
  error?: string;
  selectRef: RefObject<HTMLSelectElement | null>;
}) {
  const id = useId();
  const messageId = `${id}-message`;
  const message = error ?? "Only the area is used, never your address.";

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-xs font-semibold text-ink">
        Neighbourhood
      </label>
      <select
        id={id}
        ref={selectRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={messageId}
        className={cn(
          "h-11 w-full rounded-sm border bg-white px-3 text-sm outline-none transition-colors focus:ring-2",
          value ? "text-ink" : "text-subtle",
          error
            ? "border-danger focus:ring-danger/20"
            : "border-line focus:border-ink focus:ring-ink/10",
        )}
      >
        <option value="" disabled>
          Select your neighbourhood
        </option>
        {choices.map((choice) => (
          <option key={choice} value={choice} className="text-ink">
            {choice}
          </option>
        ))}
      </select>
      <p id={messageId} className={cn("text-xs", error ? "text-danger" : "text-muted")}>
        {message}
      </p>
    </div>
  );
}
