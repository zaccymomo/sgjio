import { Alert, Button, Dialog } from "@sgjio/ui";

import type { LessonSummary } from "../lib/content";
import { lessonTitle } from "../lib/filter";

/** Confirm removal of a draft that has never been published. */
export function ConfirmLessonDeleteDialog({
  lesson,
  busy,
  error,
  onCancel,
  onConfirm,
}: {
  lesson: LessonSummary | null;
  busy: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <Dialog
      open={lesson !== null}
      title={lesson ? `Delete “${lessonTitle(lesson)}”?` : ""}
      onClose={onCancel}
      dismissible={!busy}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel} disabled={busy} data-autofocus>
            Cancel
          </Button>
          <Button onClick={onConfirm} loading={busy}>
            Delete draft
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3 text-sm text-muted">
        {error && <Alert tone="error">{error}</Alert>}
        <p>
          This draft has never been published, so no user has seen it. Deleting it can&rsquo;t be
          undone.
        </p>
      </div>
    </Dialog>
  );
}
