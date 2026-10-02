import { Alert, ApiError, Button, Dialog, TextField } from "@sgjio/ui";
import { useState, type FormEvent } from "react";

import type { Topic } from "../lib/content";
import { plural } from "../lib/format";

/** Same limit as the API (TopicName in api/app/schemas.py). */
const MAX_NAME = 80;

export type NameDialogState = { mode: "create" } | { mode: "rename"; topic: Topic };

/**
 * Create a topic, or rename one (SCRUM-57). Checks the obvious on the spot, and shows the
 * server's answer on the field, e.g. a name that is already taken, ignoring case.
 */
export function TopicNameDialog({
  state,
  onClose,
  onSave,
}: {
  state: NameDialogState | null;
  onClose: () => void;
  /** Throws an ApiError if the server refuses. */
  onSave: (name: string) => Promise<void>;
}) {
  const [saving, setSaving] = useState(false);
  const renaming = state?.mode === "rename" ? state.topic : null;

  return (
    <Dialog
      open={state !== null}
      title={renaming ? `Rename “${renaming.name}”` : "New topic"}
      description={
        renaming
          ? "Users see the new name on their progress circle straight away."
          : "It goes at the end of your topic list. Users see it once it has a published lesson."
      }
      onClose={onClose}
      dismissible={!saving}
    >
      <NameForm
        initial={renaming?.name ?? ""}
        submitLabel={renaming ? "Save name" : "Create topic"}
        saving={saving}
        onCancel={onClose}
        onSubmit={async (name) => {
          setSaving(true);
          try {
            await onSave(name);
          } finally {
            setSaving(false);
          }
        }}
      />
    </Dialog>
  );
}

function NameForm({
  initial,
  submitLabel,
  saving,
  onCancel,
  onSubmit,
}: {
  initial: string;
  submitLabel: string;
  saving: boolean;
  onCancel: () => void;
  onSubmit: (name: string) => Promise<void>;
}) {
  const [name, setName] = useState(initial);
  const [fieldError, setFieldError] = useState<string>();
  const [formError, setFormError] = useState<string>();
  const trimmed = name.trim();

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(undefined);
    if (trimmed === "") return setFieldError("Enter a name for the topic.");
    if (trimmed.length > MAX_NAME) {
      return setFieldError(`Use ${MAX_NAME} characters or fewer. This name has ${trimmed.length}.`);
    }
    if (trimmed === initial) return onCancel();

    setFieldError(undefined);
    try {
      await onSubmit(trimmed);
    } catch (error) {
      if (error instanceof ApiError && (error.field === "name" || error.fieldErrors.name)) {
        setFieldError(error.fieldErrors.name ?? error.message);
      } else {
        setFormError(
          error instanceof ApiError ? error.message : "Something went wrong. Please try again.",
        );
      }
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      {formError && <Alert tone="error">{formError}</Alert>}
      <TextField
        label="Topic name"
        data-autofocus
        autoComplete="off"
        value={name}
        onChange={(event) => {
          setName(event.target.value);
          setFieldError(undefined);
        }}
        error={fieldError}
        hint={`${trimmed.length} / ${MAX_NAME} characters`}
      />
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button variant="secondary" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
        <Button type="submit" loading={saving}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}

export type ConfirmState = {
  kind: "archive" | "delete";
  topic: Topic;
  /** Why the dialog changed from delete to archive, when it did. */
  reason?: string;
};

/**
 * Confirm archiving or deleting a topic. Archiving says how many published lessons will
 * disappear from users' circles, since that is what users will notice.
 */
export function ConfirmTopicDialog({
  state,
  busy,
  error,
  onCancel,
  onConfirm,
}: {
  state: ConfirmState | null;
  busy: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const topic = state?.topic;
  const archiving = state?.kind === "archive";

  return (
    <Dialog
      open={state !== null}
      title={topic ? `${archiving ? "Archive" : "Delete"} “${topic.name}”?` : ""}
      onClose={onCancel}
      dismissible={!busy}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel} disabled={busy} data-autofocus>
            Cancel
          </Button>
          <Button onClick={onConfirm} loading={busy}>
            {archiving ? "Archive topic" : "Delete topic"}
          </Button>
        </>
      }
    >
      {topic && (
        <div className="flex flex-col gap-3 text-sm text-muted">
          {state.reason && <Alert tone="info">{state.reason}</Alert>}
          {error && <Alert tone="error">{error}</Alert>}
          {archiving ? (
            <>
              <p>
                Users will no longer see this topic.{" "}
                {topic.published_count > 0 ? (
                  <strong className="font-semibold text-ink">
                    Its {plural(topic.published_count, "published lesson")} will disappear from
                    users&rsquo; progress circles, and their overall progress figure will drop to
                    match.
                  </strong>
                ) : (
                  "It has no published lessons, so nothing changes on users' home page."
                )}
              </p>
              <p>
                Its lessons and everyone&rsquo;s progress are kept. You can restore the topic at any
                time from Archived topics.
              </p>
            </>
          ) : (
            <p>
              The topic has no lessons, so nothing else is affected. This can&rsquo;t be undone.
            </p>
          )}
        </div>
      )}
    </Dialog>
  );
}
