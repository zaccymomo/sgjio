import { Alert, ApiError, Button, Dialog, TextField } from "@sgjio/ui";
import { useState, type FormEvent } from "react";

import { validateTopicName, type Topic } from "../lib/topics";
import { DialogActions } from "./DialogActions";

/** What the dialog is for. `null` keeps it closed. */
export type TopicFormMode = { kind: "create" } | { kind: "rename"; topic: Topic } | null;

/** One dialog for "New topic" and "Rename topic". */
export function TopicFormDialog({
  mode,
  topics,
  onSubmit,
  onClose,
}: {
  mode: TopicFormMode;
  /** Every topic, so a name clash with an archived one can say where to look. */
  topics: Topic[];
  /** Resolves when the change went through. Rejects with the API's error otherwise. */
  onSubmit: (name: string) => Promise<void>;
  onClose: () => void;
}) {
  const [busy, setBusy] = useState(false);

  async function submit(name: string) {
    setBusy(true);
    try {
      await onSubmit(name);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={mode !== null}
      title={mode?.kind === "rename" ? "Rename topic" : "New topic"}
      onClose={onClose}
      dismissible={!busy}
    >
      {mode && (
        <TopicForm
          initialName={mode.kind === "rename" ? mode.topic.name : ""}
          submitLabel={mode.kind === "rename" ? "Save" : "Add topic"}
          archivedNames={topics.filter((t) => t.archived_at).map((t) => t.name.toLowerCase())}
          busy={busy}
          onSubmit={submit}
          onCancel={onClose}
        />
      )}
    </Dialog>
  );
}

// Mounted fresh each time the dialog opens, so the field and its errors start clean.
function TopicForm({
  initialName,
  submitLabel,
  archivedNames,
  busy,
  onSubmit,
  onCancel,
}: {
  initialName: string;
  submitLabel: string;
  archivedNames: string[];
  busy: boolean;
  onSubmit: (name: string) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState(initialName);
  const [fieldError, setFieldError] = useState<string>();
  const [formError, setFormError] = useState<string>();

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(undefined);
    const problem = validateTopicName(name);
    setFieldError(problem ?? undefined);
    if (problem) return;

    const trimmed = name.trim();
    // Nothing changed: there is nothing to save. A change of capitals only is a real change.
    if (initialName && trimmed === initialName) return onCancel();

    try {
      await onSubmit(trimmed);
    } catch (error) {
      if (!(error instanceof ApiError)) {
        setFormError("Something went wrong. Please try again.");
      } else if (error.code === "topic_name_taken") {
        setFieldError(
          archivedNames.includes(trimmed.toLowerCase())
            ? `${error.message} It matches an archived topic, so check the Archived section.`
            : error.message,
        );
      } else if (error.field === "name" || error.fieldErrors.name) {
        setFieldError(error.field === "name" ? error.message : error.fieldErrors.name);
      } else {
        setFormError(error.message);
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
        onChange={(event) => setName(event.target.value)}
        error={fieldError}
        hint="Up to 80 characters. Users see this name on their progress circle."
      />
      <DialogActions>
        <Button variant="secondary" disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" loading={busy} className="sm:min-w-24">
          {submitLabel}
        </Button>
      </DialogActions>
    </form>
  );
}
