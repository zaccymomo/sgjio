import { Alert, ApiError, Button, cn } from "@sgjio/ui";
import { Check, ChevronDown, Heart, Languages, MapPin, type LucideIcon } from "lucide-react";
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
  showProgress = false,
}: {
  initial: Profile;
  options: ProfileOptions;
  submitLabel: string;
  onSaved: (profile: Profile) => void;
  /** e.g. "Skip for now" or "Cancel", shown beside the submit button. */
  secondaryAction?: ReactNode;
  /** Show "2 of 3 done" above the form, for onboarding. */
  showProgress?: boolean;
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

  const done = [interests.length > 0, languages.length > 0, !!neighbourhood].filter(Boolean).length;

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

  const missingCount = FIELD_ORDER.filter((field) => errors[field]).length;

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      {showProgress && <Progress done={done} total={FIELD_ORDER.length} />}

      {formError && <Alert tone="error">{formError}</Alert>}
      {missingCount > 0 && (
        <Alert tone="error">
          {missingCount === 1
            ? "One section still needs an answer."
            : `${missingCount} sections still need an answer.`}
        </Alert>
      )}

      <Section
        icon={Heart}
        title="What are you into?"
        description="Pick as many as you like. We use these to suggest lessons and buddies."
        error={errors.interests}
      >
        <ChoiceGroup
          legend="Interests"
          choices={options.interests}
          selected={interests}
          collapsedCount={12}
          onToggle={(value) => {
            setInterests((current) => toggle(current, value));
            setErrors((current) => ({ ...current, interests: undefined }));
          }}
          error={errors.interests}
          firstRef={interestsRef}
        />
      </Section>

      <Section
        icon={Languages}
        title="Which languages do you speak?"
        description="Include any you're comfortable chatting in, not just your first language."
        error={errors.languages}
      >
        <ChoiceGroup
          legend="Languages you speak"
          choices={options.languages}
          selected={languages}
          collapsedCount={8}
          onToggle={(value) => {
            setLanguages((current) => toggle(current, value));
            setErrors((current) => ({ ...current, languages: undefined }));
          }}
          error={errors.languages}
          firstRef={languagesRef}
        />
      </Section>

      <Section
        icon={MapPin}
        title="Where do you live?"
        description="Only the area is used, to find buddies near you. We never ask for your address."
        error={errors.neighbourhood}
      >
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
      </Section>

      <div className="flex flex-col gap-2 pt-2 sm:flex-row-reverse sm:justify-start">
        <Button type="submit" loading={submitting} className="sm:min-w-40">
          {submitLabel}
        </Button>
        {secondaryAction}
      </div>
    </form>
  );
}

function Progress({ done, total }: { done: number; total: number }) {
  return (
    <div className="flex items-center gap-3" aria-live="polite">
      <div
        className="h-1.5 flex-1 overflow-hidden rounded-full bg-line"
        role="progressbar"
        aria-label="Profile progress"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={done}
      >
        <div
          className="h-full rounded-full bg-brand transition-[width] duration-300"
          style={{ width: `${(done / total) * 100}%` }}
        />
      </div>
      <span className="shrink-0 text-caption font-medium text-muted">
        {done} of {total} done
      </span>
    </div>
  );
}

/** One question of the form, as a card. It turns red while its answer is missing. */
function Section({
  icon: Icon,
  title,
  description,
  error,
  children,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <section
      className={cn(
        "rounded-lg border bg-white p-4 transition-colors sm:p-5",
        error ? "border-danger" : "border-line",
      )}
    >
      <div className="mb-4 flex items-start gap-3">
        <div
          className={cn(
            "flex size-9 shrink-0 items-center justify-center rounded-full",
            error ? "bg-danger-soft text-danger" : "bg-brand-soft text-brand",
          )}
        >
          <Icon className="size-4" aria-hidden />
        </div>
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-ink">{title}</h2>
          <p className="mt-0.5 text-sm text-muted">{description}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

/**
 * A set of on/off chips, each a button with aria-pressed. Long lists start collapsed
 * (anything already selected always stays visible) with a button to show the rest.
 */
function ChoiceGroup({
  legend,
  choices,
  selected,
  collapsedCount,
  onToggle,
  error,
  firstRef,
}: {
  legend: string;
  choices: string[];
  selected: string[];
  collapsedCount: number;
  onToggle: (value: string) => void;
  error?: string;
  firstRef: RefObject<HTMLButtonElement | null>;
}) {
  const messageId = useId();
  const [expanded, setExpanded] = useState(false);
  const canCollapse = choices.length > collapsedCount;
  const visible =
    expanded || !canCollapse
      ? choices
      : choices.filter((choice, index) => index < collapsedCount || selected.includes(choice));
  const hidden = choices.length - visible.length;

  return (
    <fieldset aria-describedby={error ? messageId : undefined}>
      <legend className="sr-only">{legend}</legend>
      <div className="flex flex-wrap gap-2">
        {visible.map((choice, index) => {
          const on = selected.includes(choice);
          return (
            <button
              key={choice}
              ref={index === 0 ? firstRef : undefined}
              type="button"
              aria-pressed={on}
              onClick={() => onToggle(choice)}
              className={cn(
                "inline-flex h-9 items-center gap-1.5 rounded-full border px-3.5 text-sm transition-colors",
                "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
                on
                  ? "border-brand bg-brand-soft font-medium text-ink"
                  : "border-line bg-white text-muted hover:border-subtle hover:text-ink",
              )}
            >
              {on && <Check className="size-3.5 text-brand" aria-hidden />}
              {choice}
            </button>
          );
        })}
        {canCollapse && (hidden > 0 || expanded) && (
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            aria-expanded={expanded}
            className="inline-flex h-9 items-center gap-1 rounded-full px-3 text-sm font-semibold text-brand hover:bg-brand-soft focus-visible:outline-2 focus-visible:outline-brand"
          >
            {expanded ? "Show fewer" : `Show ${hidden} more`}
            <ChevronDown
              className={cn("size-4 transition-transform", expanded && "rotate-180")}
              aria-hidden
            />
          </button>
        )}
      </div>
      {error ? (
        <p id={messageId} className="mt-3 text-xs text-danger">
          {error}
        </p>
      ) : (
        <p className="mt-3 text-xs text-muted">
          {selected.length === 0 ? "None selected yet" : `${selected.length} selected`}
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

  return (
    <div className="flex flex-col gap-1.5">
      {/* The section heading already asks the question; the label is for screen readers. */}
      <label htmlFor={id} className="sr-only">
        Neighbourhood
      </label>
      <div className="relative">
        <MapPin
          className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle"
          aria-hidden
        />
        <select
          id={id}
          ref={selectRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? messageId : undefined}
          className={cn(
            "h-11 w-full appearance-none rounded-sm border bg-white pr-10 pl-9 text-sm outline-none transition-colors focus:ring-2",
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
        <ChevronDown
          className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-subtle"
          aria-hidden
        />
      </div>
      {error && (
        <p id={messageId} className="text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
