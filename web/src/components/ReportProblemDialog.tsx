import { Alert, ApiError, Button, Dialog, TextAreaField, apiFetch, cn } from "@sgjio/ui";
import { useState, type FormEvent } from "react";

/** The reasons SCRUM-82 AC1 lists, in its order. Values match services/content/app/models.py ReportReason. */
const REASONS = [
  { value: "wrong", label: "Wrong or outdated" },
  { value: "insensitive", label: "Insensitive" },
  { value: "typo", label: "Typo" },
  { value: "media", label: "Image or audio not working" },
  { value: "other", label: "Other" },
] as const;

type Reason = (typeof REASONS)[number]["value"];

const MAX_NOTE = 500;

/**
 * "Report a problem" on a lesson card (SCRUM-82): pick a reason, add an optional note of up
 * to 500 characters, and send (AC1). The report names the lesson, the version shown and the
 * card (AC3). Sending closes the dialog and the page says thanks, leaving the learner on the
 * same card (AC2): the deck behind it never moves.
 */
export function ReportProblemDialog({
  open,
  lessonId,
  version,
  cardId,
  cardNumber,
  onClose,
  onSent,
}: {
  open: boolean;
  lessonId: string;
  version: number;
  cardId: string;
  /** 1-based, for the dialog's description. */
  cardNumber: number;
  onClose: () => void;
  onSent: () => void;
}) {
  return (
    <Dialog
      open={open}
      title="Report a problem"
      description={`Tell us what's wrong with card ${cardNumber}, and we'll look into it.`}
      onClose={onClose}
    >
      {/* Mounted only while open (Dialog's children), so each report starts empty. */}
      <ReportForm
        lessonId={lessonId}
        version={version}
        cardId={cardId}
        onCancel={onClose}
        onSent={onSent}
      />
    </Dialog>
  );
}

function ReportForm({
  lessonId,
  version,
  cardId,
  onCancel,
  onSent,
}: {
  lessonId: string;
  version: number;
  cardId: string;
  onCancel: () => void;
  onSent: () => void;
}) {
  const [reason, setReason] = useState<Reason | null>(null);
  const [note, setNote] = useState("");
  const [missingReason, setMissingReason] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!reason) {
      setMissingReason(true);
      return;
    }
    setSending(true);
    setError(null);
    try {
      await apiFetch(`/api/lessons/${lessonId}/reports`, {
        method: "POST",
        body: { version, card_id: cardId, reason, note },
      });
      onSent();
    } catch (failure) {
      setError(
        failure instanceof ApiError && failure.status !== 0
          ? failure.message
          : "We couldn't send your report. Check your connection and try again.",
      );
      setSending(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-4">
      <fieldset aria-describedby={missingReason ? "report-reason-error" : undefined}>
        <legend className="text-xs font-semibold text-ink">What&apos;s the problem?</legend>
        <div className="mt-1.5 flex flex-col gap-1.5">
          {REASONS.map((option, n) => (
            <label
              key={option.value}
              className={cn(
                "flex cursor-pointer items-center gap-2.5 rounded-sm border px-3 py-2.5 text-sm text-ink transition-colors",
                reason === option.value
                  ? "border-brand bg-brand-soft/50"
                  : missingReason
                    ? "border-danger"
                    : "border-line hover:bg-surface",
              )}
            >
              <input
                type="radio"
                name="reason"
                value={option.value}
                checked={reason === option.value}
                onChange={() => {
                  setReason(option.value);
                  setMissingReason(false);
                }}
                data-autofocus={n === 0 ? true : undefined}
                className="size-4 accent-brand"
              />
              {option.label}
            </label>
          ))}
        </div>
        {missingReason && (
          <p id="report-reason-error" className="mt-1.5 text-xs text-danger">
            Select what the problem is.
          </p>
        )}
      </fieldset>

      <TextAreaField
        label="Add a note (optional)"
        value={note}
        onChange={(event) => setNote(event.target.value)}
        maxLength={MAX_NOTE}
        hint={`${note.length} / ${MAX_NOTE} characters`}
        placeholder="What should it say instead?"
      />

      {error && <Alert tone="error">{error}</Alert>}

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button type="button" variant="secondary" onClick={onCancel} disabled={sending}>
          Cancel
        </Button>
        <Button type="submit" loading={sending}>
          Send report
        </Button>
      </div>
    </form>
  );
}
