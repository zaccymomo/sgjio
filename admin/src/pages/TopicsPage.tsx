import { Alert, ApiError, Button, ErrorState, Spinner } from "@sgjio/ui";
import { ChevronRight, Plus } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ConfirmTopicDialog, type TopicConfirm } from "../components/ConfirmTopicDialog";
import { TopicFormDialog, type TopicFormMode } from "../components/TopicFormDialog";
import { TopicRow } from "../components/TopicRow";
import {
  archiveTopic,
  createTopic,
  deleteTopic,
  renameTopic,
  restoreTopic,
  useTopics,
  type Topic,
} from "../lib/topics";

type DialogState =
  | { kind: "create" }
  | { kind: "rename"; id: string }
  | { kind: "archive" | "delete"; id: string; notice?: string }
  | null;

type Notice = { tone: "success" | "error"; text: string };

const LIST = "divide-y divide-line overflow-hidden rounded-lg border border-line bg-white";

/**
 * Create, rename, archive, restore and delete topics (SCRUM-57). A topic is a group of
 * lessons and shows as one progress circle on users' home screen.
 *
 * Archiving hides a topic from users and keeps its lessons and progress. Deleting is only
 * possible for a topic with no lessons, so which of the two a row offers depends on its
 * lesson count: the server never decides for us.
 */
export function TopicsPage() {
  const { state, reload, run } = useTopics();
  const [dialog, setDialog] = useState<DialogState>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [restoringId, setRestoringId] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [focusRequest, setFocusRequest] = useState(0);
  const focusDone = useRef(0);

  const topics = state.status === "ready" ? state.topics : [];
  const active = topics.filter((topic) => !topic.archived_at);
  const archived = topics.filter((topic) => topic.archived_at);

  // Look the topic up in the latest list rather than keeping a copy, so the dialog never
  // shows lesson counts that have since changed. If it has gone, the dialog closes itself.
  const target = dialog && "id" in dialog ? topics.find((t) => t.id === dialog.id) : undefined;
  const formMode: TopicFormMode =
    dialog?.kind === "create"
      ? { kind: "create" }
      : dialog?.kind === "rename" && target
        ? { kind: "rename", topic: target }
        : null;
  const confirm: TopicConfirm =
    (dialog?.kind === "archive" || dialog?.kind === "delete") && target
      ? { kind: dialog.kind, topic: target, notice: dialog.notice }
      : null;

  function open(next: DialogState) {
    setNotice(null);
    setDialog(next);
  }

  function finish(text: string) {
    setDialog(null);
    setNotice({ tone: "success", text });
  }

  // After a row disappears, the browser has nowhere sensible to return focus to, so it goes
  // to the heading, just above the confirmation message. This waits until no dialog is open:
  // while one is, the page behind it is inert and refuses focus.
  useEffect(() => {
    if (focusRequest === focusDone.current || dialog !== null) return;
    focusDone.current = focusRequest;
    headingRef.current?.focus();
  }, [focusRequest, dialog]);

  function focusHeading() {
    setFocusRequest((count) => count + 1);
  }

  /** Someone else removed the topic meanwhile: say so, and the refreshed list shows it gone. */
  function handledMissing(error: unknown): boolean {
    if (!(error instanceof ApiError) || error.code !== "topic_not_found") return false;
    setDialog(null);
    setNotice({ tone: "error", text: "That topic no longer exists. The list has been updated." });
    return true;
  }

  async function submitForm(name: string) {
    if (!dialog) return;
    try {
      if (dialog.kind === "create") {
        const topic = await run(() => createTopic(name));
        finish(`Added “${topic.name}”.`);
      } else if (dialog.kind === "rename") {
        const topic = await run(() => renameTopic(dialog.id, name));
        finish(`Renamed to “${topic.name}”.`);
      }
    } catch (error) {
      if (!handledMissing(error)) throw error;
    }
  }

  async function confirmAction() {
    if (dialog?.kind !== "archive" && dialog?.kind !== "delete") return;
    const { kind, id } = dialog;
    const name = target?.name ?? "The topic";
    try {
      if (kind === "archive") {
        await run(() => archiveTopic(id));
        finish(`Archived “${name}”. You can restore it from the Archived section.`);
      } else {
        await run(() => deleteTopic(id));
        finish(`Deleted “${name}”.`);
      }
      focusHeading();
    } catch (error) {
      if (handledMissing(error)) return;
      if (kind === "delete" && error instanceof ApiError && error.code === "topic_not_empty") {
        // A lesson was added after this page loaded. Offer the safe choice instead.
        setDialog({
          kind: "archive",
          id,
          notice:
            "A lesson was added to this topic since the page loaded, so it can't be deleted. You can archive it instead.",
        });
        return;
      }
      throw error;
    }
  }

  async function restore(topic: Topic) {
    setNotice(null);
    setRestoringId(topic.id);
    try {
      await run(() => restoreTopic(topic.id));
      setNotice({
        tone: "success",
        text: `Restored “${topic.name}”. Users can see it again.`,
      });
      focusHeading();
    } catch (error) {
      if (!handledMissing(error)) {
        setNotice({
          tone: "error",
          text:
            error instanceof ApiError ? error.message : "Something went wrong. Please try again.",
        });
      }
    } finally {
      setRestoringId(null);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 ref={headingRef} tabIndex={-1} className="text-2xl font-bold text-ink outline-none">
            Topics
          </h1>
          <p className="mt-1 max-w-xl text-sm text-muted">
            A topic groups lessons, and each one is a progress circle on users&rsquo; home screen.
          </p>
        </div>
        <Button className="sm:shrink-0" onClick={() => open({ kind: "create" })}>
          <Plus className="size-4" aria-hidden />
          New topic
        </Button>
      </div>

      {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}

      {state.status === "loading" && (
        <div className="flex justify-center py-16 text-brand">
          <Spinner className="size-6" label="Loading topics" />
        </div>
      )}

      {state.status === "error" && <ErrorState message={state.message} onRetry={reload} />}

      {state.status === "ready" && (
        <>
          <section aria-labelledby="active-topics" className="flex flex-col gap-2.5">
            <h2
              id="active-topics"
              className="text-caption font-semibold tracking-wide text-muted uppercase"
            >
              Active ({active.length})
            </h2>
            {active.length === 0 ? (
              <div className="rounded-lg border border-line bg-surface p-5 text-center">
                <p className="text-sm font-semibold text-ink">
                  {archived.length === 0 ? "No topics yet" : "No active topics"}
                </p>
                <p className="mt-1 text-sm text-muted">
                  {archived.length === 0
                    ? "Select New topic to add the first one. Lessons are grouped under topics."
                    : "Users see no progress circles. Select New topic, or restore one from Archived."}
                </p>
              </div>
            ) : (
              <ul className={LIST}>
                {active.map((topic) => (
                  <TopicRow
                    key={topic.id}
                    topic={topic}
                    onRename={() => open({ kind: "rename", id: topic.id })}
                    onRemove={() =>
                      open({ kind: topic.lesson_count === 0 ? "delete" : "archive", id: topic.id })
                    }
                    onRestore={() => undefined}
                  />
                ))}
              </ul>
            )}
          </section>

          {archived.length > 0 && (
            <details className="group rounded-lg border border-line bg-surface">
              <summary className="flex cursor-pointer list-none items-center gap-2 rounded-lg px-4 py-3 text-sm font-semibold text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand [&::-webkit-details-marker]:hidden">
                <ChevronRight
                  className="size-4 text-muted transition-transform group-open:rotate-90"
                  aria-hidden
                />
                Archived ({archived.length})
              </summary>
              <div className="border-t border-line px-4 pt-3 pb-4">
                <p className="mb-3 text-caption text-muted">
                  Hidden from users. Lessons and progress are kept, so restoring a topic brings its
                  progress circle back.
                </p>
                <ul className={LIST}>
                  {archived.map((topic) => (
                    <TopicRow
                      key={topic.id}
                      topic={topic}
                      busy={restoringId === topic.id}
                      onRename={() => open({ kind: "rename", id: topic.id })}
                      onRemove={() => undefined}
                      onRestore={() => void restore(topic)}
                    />
                  ))}
                </ul>
              </div>
            </details>
          )}
        </>
      )}

      <TopicFormDialog
        mode={formMode}
        topics={topics}
        onSubmit={submitForm}
        onClose={() => setDialog(null)}
      />
      <ConfirmTopicDialog
        confirm={confirm}
        onConfirm={confirmAction}
        onClose={() => setDialog(null)}
      />
    </div>
  );
}
