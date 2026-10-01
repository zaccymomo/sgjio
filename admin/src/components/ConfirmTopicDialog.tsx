import { Alert, ApiError, Button, Dialog } from "@sgjio/ui";
import { useState } from "react";

import type { Topic } from "../lib/topics";
import { DialogActions } from "./DialogActions";

/** What is being confirmed. `null` keeps the dialog closed. */
export type TopicConfirm = {
  kind: "archive" | "delete";
  topic: Topic;
  /** Why the dialog is showing something other than what was asked for. */
  notice?: string;
} | null;

/** Confirmation for archiving a topic, or deleting one that has no lessons. */
export function ConfirmTopicDialog({
  confirm,
  onConfirm,
  onClose,
}: {
  confirm: TopicConfirm;
  /** Resolves when the change went through. Rejects with the API's error otherwise. */
  onConfirm: () => Promise<void>;
  onClose: () => void;
}) {
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    try {
      await onConfirm();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={confirm !== null}
      title={confirm?.kind === "delete" ? "Delete topic permanently?" : "Archive topic?"}
      onClose={onClose}
      dismissible={!busy}
    >
      {/* Keyed so the error from one kind of confirmation never carries into the next. */}
      {confirm && (
        <ConfirmBody
          key={confirm.kind}
          confirm={confirm}
          busy={busy}
          onConfirm={run}
          onCancel={onClose}
        />
      )}
    </Dialog>
  );
}

function ConfirmBody({
  confirm,
  busy,
  onConfirm,
  onCancel,
}: {
  confirm: NonNullable<TopicConfirm>;
  busy: boolean;
  onConfirm: () => Promise<void>;
  onCancel: () => void;
}) {
  const { kind, topic, notice } = confirm;
  const [error, setError] = useState<string>();

  async function handleConfirm() {
    setError(undefined);
    try {
      await onConfirm();
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : "Something went wrong. Please try again.",
      );
    }
  }

  const published = topic.published_count;

  return (
    <div className="flex flex-col gap-3 text-sm text-muted">
      {error && <Alert tone="error">{error}</Alert>}
      {notice && <Alert tone="info">{notice}</Alert>}

      {kind === "archive" ? (
        <>
          <p>
            <strong className="font-semibold text-ink">{topic.name}</strong> will be hidden from
            users. Its lessons and everyone&rsquo;s progress are kept, and you can restore it at any
            time.
          </p>
          {published > 0 && (
            <Alert tone="info">
              {published === 1 ? "1 published lesson" : `${published} published lessons`} will
              disappear from users&rsquo; progress circles until you restore this topic.
            </Alert>
          )}
        </>
      ) : (
        <p>
          <strong className="font-semibold text-ink">{topic.name}</strong> has no lessons. Deleting
          it removes it for good and can&rsquo;t be undone.
        </p>
      )}

      <DialogActions>
        <Button variant="secondary" data-autofocus disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
        <Button loading={busy} onClick={handleConfirm}>
          {kind === "delete" ? "Delete permanently" : "Archive topic"}
        </Button>
      </DialogActions>
    </div>
  );
}
