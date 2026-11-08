import { Alert, ApiError, Button, Dialog, TextAreaField, TextField } from "@sgjio/ui";
import { useState, type FormEvent } from "react";

import type { Topic, TopicFields } from "../lib/content";
import { plural } from "../lib/format";

/** Same limits as the API (TopicName and TopicDescription in services/content/app/schemas.py). */
const MAX_NAME = 80;
const MAX_DESCRIPTION = 200;

export type TopicDialogState =
  | { mode: "create" }
  /** `focus` puts the cursor in the description, e.g. after "Add a description". */
  | { mode: "edit"; topic: Topic; focus?: "description" };

/**
 * Create a topic, or edit one's name and description (SCRUM-57, SCRUM-86). Checks the
 * obvious on the spot, and shows the server's answer on the field, e.g. a name that is
 * already taken, ignoring case.
 */
export function TopicDialog({
  state,
  onClose,
  onSave,
}: {
  state: TopicDialogState | null;
  onClose: () => void;
  /** Throws an ApiError if the server refuses. */
  onSave: (fields: TopicFields) => Promise<void>;
}) {
  const [saving, setSaving] = useState(false);
  const editing = state?.mode === "edit" ? state : null;

  return (
    <Dialog
      open={state !== null}
      title={editing ? `Edit “${editing.topic.name}”` : "New topic"}
      description={
        editing
          ? "Users see the name on their progress circle, and the description at the top of the topic’s page."
          : "It goes at the end of your topic list. Users see it once it has a published lesson."
      }
      onClose={onClose}
      dismissible={!saving}
    >
      <TopicForm
        initial={{
          name: editing?.topic.name ?? "",
          description: editing?.topic.description ?? "",
        }}
        focusDescription={editing?.focus === "description"}
        submitLabel={editing ? "Save topic" : "Create topic"}
        saving={saving}
        onCancel={onClose}
        onSubmit={async (fields) => {
          setSaving(true);
          try {
            await onSave(fields);
          } finally {
            setSaving(false);
          }
        }}
      />
    </Dialog>
  );
}

type FieldErrors = { name?: string; description?: string };

function TopicForm({
  initial,
  focusDescription,
  submitLabel,
  saving,
  onCancel,
  onSubmit,
}: {
  initial: TopicFields;
  focusDescription: boolean;
  submitLabel: string;
  saving: boolean;
  onCancel: () => void;
  onSubmit: (fields: TopicFields) => Promise<void>;
}) {
  const [name, setName] = useState(initial.name);
  const [description, setDescription] = useState(initial.description);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string>();
  const fields = { name: name.trim(), description: description.trim() };

  function check(): FieldErrors {
    const errors: FieldErrors = {};
    if (fields.name === "") errors.name = "Enter a name for the topic.";
    else if (fields.name.length > MAX_NAME) {
      errors.name = `Use ${MAX_NAME} characters or fewer. This name has ${fields.name.length}.`;
    }
    if (fields.description.length > MAX_DESCRIPTION) {
      errors.description = `Use ${MAX_DESCRIPTION} characters or fewer. This description has ${fields.description.length}.`;
    }
    return errors;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(undefined);
    const errors = check();
    setFieldErrors(errors);
    if (errors.name || errors.description) return;
    if (fields.name === initial.name && fields.description === initial.description) {
      return onCancel();
    }

    try {
      await onSubmit(fields);
    } catch (error) {
      if (!(error instanceof ApiError)) {
        return setFormError("Something went wrong. Please try again.");
      }
      const server: FieldErrors = {
        name: error.fieldErrors.name ?? (error.field === "name" ? error.message : undefined),
        description:
          error.fieldErrors.description ??
          (error.field === "description" ? error.message : undefined),
      };
      if (server.name || server.description) setFieldErrors(server);
      else setFormError(error.message);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      {formError && <Alert tone="error">{formError}</Alert>}
      <TextField
        label="Topic name"
        data-autofocus={focusDescription ? undefined : true}
        autoComplete="off"
        value={name}
        onChange={(event) => {
          setName(event.target.value);
          setFieldErrors(({ description }) => ({ description }));
        }}
        error={fieldErrors.name}
        hint={`${fields.name.length} / ${MAX_NAME} characters`}
      />
      <TextAreaField
        label="Description (optional)"
        data-autofocus={focusDescription ? true : undefined}
        placeholder="What learners will find in this topic, in a sentence or two."
        value={description}
        onChange={(event) => {
          setDescription(event.target.value);
          setFieldErrors(({ name }) => ({ name }));
        }}
        error={fieldErrors.description}
        hint={`${fields.description.length} / ${MAX_DESCRIPTION} characters`}
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
