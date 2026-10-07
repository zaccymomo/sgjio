import {
  Alert,
  ApiError,
  Button,
  Dialog,
  ErrorState,
  Placeholder,
  Spinner,
  useAuth,
} from "@sgjio/ui";
import { ChevronLeft, Trash2 } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { LessonForm } from "../components/LessonForm";
import { StatusBadge } from "../components/StatusBadge";
import { topicApi, type Notice, type Topic } from "../lib/content";
import { lessonTitle } from "../lib/filter";
import { formatDateTime, formatRelative } from "../lib/format";
import {
  emptyLesson,
  fieldsOf,
  lessonApi,
  lessonFieldErrors,
  sameFields,
  type Lesson,
  type LessonFieldErrors,
  type LessonFields,
} from "../lib/lessons";
import { useUnsavedChanges } from "../lib/useUnsavedChanges";

/** The path for a lesson not created yet. Nothing is saved until the first Save draft. */
const NEW = "new";

type Load =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "not-found" }
  | {
      status: "ready";
      /** The id in the address this was loaded for: a lesson's id, or "new". */
      lessonId: string;
      lesson: Lesson | null;
      topics: Topic[];
      /** Changes on every fetch, so the editor starts afresh from what was fetched. */
      key: number;
    };

/**
 * Write a lesson and save it as a draft (SCRUM-64), at /lessons/new and /lessons/:id.
 *
 * A new lesson exists only in the page until its first save, which creates the draft and
 * changes the address to /lessons/:id; that way opening the editor and leaving never
 * leaves an empty draft behind. `/lessons/new?topic=<id>` starts in that topic.
 *
 * Published and withdrawn lessons open read-only: editing and withdrawing them is SCRUM-52.
 */
export function LessonEditorPage() {
  const { id = NEW } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { refresh: recheckSession } = useAuth();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const fetches = useRef(0);
  // Set when this page has just created the lesson, so moving to its address does not
  // fetch it again and reset the editor.
  const skipLoadFor = useRef<string | null>(null);

  useEffect(() => {
    if (skipLoadFor.current === id) {
      skipLoadFor.current = null;
      return;
    }
    const controller = new AbortController();
    Promise.all([
      topicApi.list(controller.signal),
      id === NEW ? null : lessonApi.get(id, controller.signal),
    ])
      .then(([topics, lesson]) => {
        fetches.current += 1;
        setLoad({ status: "ready", lessonId: id, lesson, topics, key: fetches.current });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        // The session expired: RequireAuth sends the administrator to sign in and back.
        if (error instanceof ApiError && error.status === 401) return void recheckSession();
        // An address that is not a lesson id at all is answered as "not found" too.
        if (
          error instanceof ApiError &&
          (error.code === "lesson_not_found" || error.code === "validation_error")
        ) {
          return setLoad({ status: "not-found" });
        }
        setLoad({
          status: "error",
          message:
            error instanceof ApiError
              ? error.message
              : "We couldn't load this lesson. Please try again.",
        });
      });
    return () => controller.abort();
  }, [id, attempt, recheckSession]);

  function retry() {
    setLoad({ status: "loading" });
    setAttempt((count) => count + 1);
  }

  function handleCreated(lesson: Lesson) {
    skipLoadFor.current = lesson.id;
    setLoad((current) =>
      current.status === "ready" ? { ...current, lessonId: lesson.id, lesson } : current,
    );
    navigate(`/lessons/${lesson.id}`, { replace: true });
  }

  // Moving from one lesson to another shows the spinner until the other has loaded.
  const ready = load.status === "ready" && load.lessonId === id ? load : null;

  return (
    <div className="flex flex-col gap-4">
      <BackLink />
      {ready ? (
        <LessonEditor
          key={ready.key}
          initialLesson={ready.lesson}
          topics={ready.topics}
          presetTopicId={searchParams.get("topic")}
          onCreated={handleCreated}
        />
      ) : load.status === "error" ? (
        <ErrorState message={load.message} onRetry={retry} />
      ) : load.status === "not-found" ? (
        <section className="flex flex-col items-center gap-3 rounded-lg border border-line bg-white p-6 text-center">
          <h1 className="text-base font-bold text-ink">That lesson no longer exists</h1>
          <p className="text-sm text-muted">
            It may have been deleted. Your other lessons are on the content page.
          </p>
          <Button variant="secondary" onClick={() => navigate("/")}>
            Go to all content
          </Button>
        </section>
      ) : (
        <div className="flex justify-center py-16 text-brand">
          <Spinner className="size-6" label="Loading the lesson" />
        </div>
      )}
    </div>
  );
}

function BackLink() {
  return (
    <Link
      to="/"
      className="inline-flex w-fit items-center gap-1 rounded-sm text-sm font-medium text-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
    >
      <ChevronLeft className="size-4" aria-hidden />
      All content
    </Link>
  );
}

/** A refusal shown above the form, with what the administrator can do about it. */
type Problem = { message: ReactNode; action?: { label: string; onSelect: () => void } };

const OUT_OF_DATE =
  "This draft was changed in another tab or by another administrator since you opened it, " +
  "so your changes weren't saved. Copy anything you want to keep, then load the latest version.";

function LessonEditor({
  initialLesson,
  topics: initialTopics,
  presetTopicId,
  onCreated,
}: {
  /** Null for a lesson that has not been saved yet. */
  initialLesson: Lesson | null;
  topics: Topic[];
  /** From ?topic=, for "Add lesson" on a topic. Ignored unless it is an active topic. */
  presetTopicId: string | null;
  onCreated: (lesson: Lesson) => void;
}) {
  const navigate = useNavigate();
  const [lesson, setLesson] = useState(initialLesson);
  const [topics, setTopics] = useState(initialTopics);
  const [saved, setSaved] = useState<LessonFields>(() => {
    if (initialLesson) return fieldsOf(initialLesson);
    const preset = initialTopics.find(
      (topic) => topic.id === presetTopicId && topic.archived_at === null,
    );
    return emptyLesson(preset?.id ?? null);
  });
  const [form, setForm] = useState(saved);
  const [errors, setErrors] = useState<LessonFieldErrors>({});
  const [problem, setProblem] = useState<Problem | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const editable = lesson === null || lesson.status === "draft";
  const dirty = editable && !sameFields(form, saved);
  const { blocker, allowNavigation } = useUnsavedChanges(dirty);

  function edit(next: LessonFields) {
    setForm(next);
    // A field's error goes once that field is changed.
    setErrors((current) => {
      const kept = { ...current };
      for (const key of Object.keys(kept) as (keyof LessonFields)[]) {
        if (next[key] !== form[key]) delete kept[key];
      }
      return kept;
    });
  }

  function goToContent(notice: Notice) {
    allowNavigation();
    navigate("/", { state: { notice } });
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (saving || !editable) return;
    const fieldErrors = lessonFieldErrors(form);
    setErrors(fieldErrors);
    setProblem(null);
    if (Object.keys(fieldErrors).length > 0) return;

    const sent = form;
    setSaving(true);
    try {
      const result = lesson ? await lessonApi.update(lesson, sent) : await lessonApi.create(sent);
      const resultFields = fieldsOf(result);
      setLesson(result);
      setSaved(resultFields);
      // Keep anything typed while the save was running.
      setForm((now) => (sameFields(now, sent) ? resultFields : now));
      if (!lesson) {
        allowNavigation();
        onCreated(result);
      }
    } catch (error) {
      showSaveError(error);
    } finally {
      setSaving(false);
    }
  }

  function showSaveError(error: unknown) {
    if (!(error instanceof ApiError)) {
      setProblem({
        message: "Something went wrong, so the lesson wasn't saved. Please try again.",
      });
      return;
    }
    if (error.status === 401) {
      // Not re-checking the session here: that would replace the editor with the sign-in
      // page and lose what was typed.
      setProblem({
        message: (
          <>
            You&rsquo;ve been signed out, so the lesson wasn&rsquo;t saved.{" "}
            <a
              href="/sign-in"
              target="_blank"
              rel="noopener"
              className="font-semibold underline underline-offset-2"
            >
              Sign in again in a new tab
            </a>
            , then select Save draft again.
          </>
        ),
      });
      return;
    }
    switch (error.code) {
      case "validation_error": {
        const { title, topic_id } = error.fieldErrors;
        const fieldErrors = Object.fromEntries(
          Object.entries({ title, topic_id }).filter(([, message]) => message),
        );
        setErrors(fieldErrors);
        if (Object.keys(fieldErrors).length === 0) setProblem({ message: error.message });
        return;
      }
      case "topic_not_found":
      case "topic_archived":
        setErrors({ topic_id: error.message });
        // The topic list is out of date; fetch it so the choice matches what exists.
        topicApi
          .list()
          .then(setTopics)
          .catch(() => {});
        return;
      case "lesson_out_of_date":
        setProblem({
          message: OUT_OF_DATE,
          action: { label: "Load the latest version", onSelect: () => void loadLatest() },
        });
        return;
      case "lesson_not_draft":
        setProblem({
          message:
            "This lesson has been published since you opened it, so it can't be edited here. " +
            "Copy anything you want to keep, then reload it.",
          action: { label: "Reload the lesson", onSelect: () => void loadLatest() },
        });
        return;
      case "lesson_not_found":
        setProblem({
          message:
            "This lesson has been deleted since you opened it, so your changes weren't saved. " +
            "Copy anything you want to keep.",
        });
        return;
      default:
        setProblem({ message: `The lesson wasn't saved. ${error.message}` });
    }
  }

  /** Replace what is on screen with the lesson as it is now on the server. */
  async function loadLatest() {
    if (!lesson) return;
    setProblem(null);
    try {
      const [latest, latestTopics] = await Promise.all([lessonApi.get(lesson.id), topicApi.list()]);
      setLesson(latest);
      setTopics(latestTopics);
      setSaved(fieldsOf(latest));
      setForm(fieldsOf(latest));
      setErrors({});
    } catch (error) {
      setProblem({
        message:
          error instanceof ApiError && error.code === "lesson_not_found"
            ? "This lesson has been deleted since you opened it."
            : "We couldn't load the latest version. Please try again.",
        action:
          error instanceof ApiError && error.code === "lesson_not_found"
            ? undefined
            : { label: "Try again", onSelect: () => void loadLatest() },
      });
    }
  }

  async function remove() {
    if (!lesson) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await lessonApi.remove(lesson);
      goToContent({ tone: "success", message: `“${lessonTitle(lesson)}” is deleted.` });
    } catch (error) {
      if (error instanceof ApiError && error.code === "lesson_not_found") {
        goToContent({ tone: "info", message: "That lesson had already been deleted." });
      } else if (error instanceof ApiError && error.code === "lesson_out_of_date") {
        setConfirmingDelete(false);
        setProblem({
          message:
            "This draft was changed in another tab or by another administrator since you " +
            "opened it, so it wasn't deleted. Load the latest version and check it first.",
          action: { label: "Load the latest version", onSelect: () => void loadLatest() },
        });
      } else {
        setDeleteError(
          error instanceof ApiError ? error.message : "Something went wrong. Please try again.",
        );
      }
    } finally {
      setDeleting(false);
    }
  }

  const heading = lesson === null ? "New lesson" : editable ? "Edit draft" : "Lesson";
  const status = saving
    ? "Saving…"
    : dirty
      ? "Unsaved changes"
      : lesson
        ? `Saved ${formatRelative(lesson.updated_at)}`
        : "Not saved yet";

  return (
    <>
      <form onSubmit={save} noValidate className="flex flex-col gap-5">
        {/* Stays at the top while scrolling a long lesson, so Save is always in reach. */}
        <div className="sticky top-0 z-10 -mx-4 flex flex-col gap-3 border-b border-line bg-surface/95 px-4 py-3 backdrop-blur sm:flex-row sm:items-center sm:justify-between md:-mx-6 md:px-6">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <h1 className="text-2xl font-bold text-ink">{heading}</h1>
              {lesson && <StatusBadge status={lesson.status} />}
            </div>
            {editable && (
              <p aria-live="polite" className="mt-0.5 text-caption text-muted">
                <span title={lesson ? `Saved ${formatDateTime(lesson.updated_at)}` : undefined}>
                  {status}
                </span>
                <span aria-hidden> · </span>
                Drafts are only visible to administrators.
              </p>
            )}
          </div>
          {editable && (
            <div className="flex gap-2">
              {lesson?.deletable && (
                <Button
                  variant="secondary"
                  className="flex-1 sm:flex-none"
                  onClick={() => {
                    setDeleteError(null);
                    setConfirmingDelete(true);
                  }}
                  disabled={saving}
                >
                  <Trash2 className="size-4" aria-hidden />
                  Delete
                </Button>
              )}
              <Button
                type="submit"
                className="flex-1 sm:flex-none"
                loading={saving}
                // An unchanged lesson has nothing to save. A new one can be saved empty.
                disabled={lesson !== null && !dirty}
              >
                Save draft
              </Button>
            </div>
          )}
        </div>

        <div className="flex max-w-3xl flex-col gap-5">
          {problem && (
            <Alert tone="error">
              <div className="flex flex-col items-start gap-2">
                <p>{problem.message}</p>
                {problem.action && (
                  <Button variant="secondary" size="sm" onClick={problem.action.onSelect}>
                    {problem.action.label}
                  </Button>
                )}
              </div>
            </Alert>
          )}

          {!editable && (
            <Placeholder story="SCRUM-52" title="Editing published lessons">
              This lesson has been {lesson?.status === "withdrawn" ? "withdrawn" : "published"}, so
              it is shown read-only. Editing and withdrawing published lessons is not available yet.
            </Placeholder>
          )}

          <section className="rounded-lg border border-line bg-white p-4 sm:p-6">
            <LessonForm
              value={form}
              onChange={edit}
              errors={errors}
              topics={topics}
              savedTopicId={saved.topic_id}
              readOnly={!editable}
            />
          </section>

          <Placeholder story="SCRUM-19" title="Cards">
            Lessons are now decks of cards. Writing them here arrives with the card editor.
          </Placeholder>
        </div>
      </form>

      <Dialog
        open={confirmingDelete}
        title={lesson ? `Delete “${lessonTitle(lesson)}”?` : ""}
        onClose={() => setConfirmingDelete(false)}
        dismissible={!deleting}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setConfirmingDelete(false)}
              disabled={deleting}
              data-autofocus
            >
              Cancel
            </Button>
            <Button onClick={() => void remove()} loading={deleting}>
              Delete draft
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3 text-sm text-muted">
          {deleteError && <Alert tone="error">{deleteError}</Alert>}
          <p>
            This draft has never been published, so no user has seen it. Deleting it can&rsquo;t be
            undone.
            {dirty && " Your unsaved changes will be lost too."}
          </p>
        </div>
      </Dialog>

      {/* SCRUM-64 AC6, for leaving within the portal. Closing the tab gets the browser's own. */}
      <Dialog
        open={blocker.state === "blocked"}
        title="Leave without saving?"
        onClose={() => blocker.reset?.()}
        footer={
          <>
            <Button variant="secondary" onClick={() => blocker.reset?.()} data-autofocus>
              Keep editing
            </Button>
            <Button onClick={() => blocker.proceed?.()}>Leave without saving</Button>
          </>
        }
      >
        <p className="text-sm text-muted">
          Your changes to this lesson haven&rsquo;t been saved. If you leave now, they&rsquo;ll be
          lost.
        </p>
      </Dialog>
    </>
  );
}
