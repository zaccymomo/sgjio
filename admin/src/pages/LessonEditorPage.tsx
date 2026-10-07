import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Alert, ApiError, Button, cn, ErrorState, Spinner, useAuth } from "@sgjio/ui";
import {
  checkLocally,
  LessonDeck,
  readingLabel,
  toLearnerCards,
  type Asset,
  type Card,
  type Issue,
} from "@sgjio/ui/lesson";
import {
  ArchiveRestore,
  ChevronLeft,
  CircleAlert,
  CloudOff,
  Ellipsis,
  Eye,
  EyeOff,
  RotateCcw,
  Send,
  Trash2,
  Undo2,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { CardEditor } from "../components/editor/CardEditor";
import { CardRail } from "../components/editor/CardRail";
import { ConfirmDialog, IssuesDialog } from "../components/editor/EditorDialogs";
import { LessonDetails } from "../components/LessonDetails";
import { LessonPreview } from "../components/LessonPreview";
import { StatusBadge } from "../components/StatusBadge";
import {
  duplicateCard,
  insertCard,
  newCard,
  removeCard,
  reorderCards,
  updateCard,
  type Preset,
} from "../lib/cards";
import { topicApi, type Notice, type Topic } from "../lib/content";
import { lessonTitle } from "../lib/filter";
import { formatDateTime, formatRelative } from "../lib/format";
import { draftOf, lessonApi, type Draft, type Lesson } from "../lib/lessons";
import { useAutosave, type SaveStatus } from "../lib/useAutosave";
import { useUnsavedChanges } from "../lib/useUnsavedChanges";

/** The path for a lesson not created yet. Nothing is saved until the first change. */
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
 * Writing a lesson as a deck of cards (SCRUM-19, SCRUM-64), at /lessons/new and /lessons/:id,
 * and publishing, withdrawing and restoring it (SCRUM-52).
 *
 * A new lesson exists only in the page until its first change, which creates it and changes
 * the address to /lessons/:id; that way opening the editor and leaving never leaves an empty
 * lesson behind. `/lessons/new?topic=<id>` starts in that topic.
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

  if (ready) {
    return (
      <LessonEditor
        key={ready.key}
        initialLesson={ready.lesson}
        topics={ready.topics}
        presetTopicId={searchParams.get("topic")}
        onCreated={handleCreated}
      />
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <BackLink />
      {load.status === "error" ? (
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

function SaveIndicator({
  status,
  lesson,
  onRetry,
}: {
  status: SaveStatus;
  lesson: Lesson | null;
  onRetry: () => void;
}) {
  if (status === "saving" || status === "pending") {
    return (
      <span className="flex items-center gap-1.5 text-xs text-muted" aria-live="polite">
        <Spinner className="size-3" /> Saving…
      </span>
    );
  }
  if (status === "error" || status === "conflict" || status === "signed-out") {
    return (
      <span
        className="flex items-center gap-1.5 text-xs font-semibold text-danger"
        aria-live="polite"
      >
        <CloudOff className="size-3.5" aria-hidden />
        Not saved
        {status === "error" && (
          <button type="button" onClick={onRetry} className="underline underline-offset-2">
            Try again
          </button>
        )}
      </span>
    );
  }
  return (
    <span className="text-xs text-muted" aria-live="polite">
      {lesson ? (
        <span title={`Saved ${formatDateTime(lesson.updated_at)}`}>
          Saved {formatRelative(lesson.updated_at)}
        </span>
      ) : (
        "Nothing saved yet"
      )}
    </span>
  );
}

type Action = "publish" | "discard" | "withdraw" | "restore" | "delete";

const DONE: Record<Exclude<Action, "delete">, string> = {
  publish: "published",
  discard: "discarded",
  withdraw: "withdrawn",
  restore: "restored",
};

type Toast = { message: string; undo?: () => void };

type MenuAction = { label: string; icon: typeof Trash2; onSelect: () => void; danger?: boolean };

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
  const [draft, setDraft] = useState<Draft>(() => {
    if (initialLesson) return draftOf(initialLesson);
    const preset = initialTopics.find(
      (topic) => topic.id === presetTopicId && topic.archived_at === null,
    );
    return { title: "", summary: "", topic_id: preset?.id ?? null, doc: { cards: [newCard()] } };
  });
  const [assets, setAssets] = useState<Record<string, Asset>>(initialLesson?.assets ?? {});
  const [selectedId, setSelectedId] = useState<string | null>(draft.doc.cards[0]?.id ?? null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [action, setAction] = useState<Action | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [issuesShown, setIssuesShown] = useState<Issue[] | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [leaveFailed, setLeaveFailed] = useState(false);
  // The newest version of the lesson from the server, for actions run after an await.
  const latest = useRef(initialLesson);
  // Lets the move to a new lesson's own address through the unsaved-changes guard.
  const allowNext = useRef<() => void>(() => {});

  const autosave = useAutosave({
    lesson,
    draft,
    onSaved: (saved, created) => {
      latest.current = saved;
      setLesson(saved);
      setAssets((current) => ({ ...current, ...saved.assets }));
      if (created) {
        allowNext.current();
        onCreated(saved);
      }
    },
  });
  const { flush, adopt } = autosave;

  // Leaving within the portal: save first, then go. Only ask if the save fails.
  const { blocker, allowNavigation } = useUnsavedChanges(autosave.dirty);
  useEffect(() => {
    allowNext.current = allowNavigation;
  }, [allowNavigation]);
  useEffect(() => {
    if (blocker.state !== "blocked") return;
    void flush().then((ok) => {
      if (ok) blocker.proceed?.();
      else setLeaveFailed(true);
    });
  }, [blocker, flush]);

  // A toast fades after a few seconds.
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 6000);
    return () => clearTimeout(timer);
  }, [toast]);

  const cards = draft.doc.cards;
  const selectedIndex = Math.max(
    0,
    cards.findIndex((card) => card.id === selectedId),
  );
  const selected: Card | undefined = cards[selectedIndex];
  const issues = useMemo(() => lesson?.issues ?? [], [lesson]);
  const blockers = issues.filter((issue) => issue.severity === "blocker");
  const topic = topics.find((t) => t.id === draft.topic_id) ?? null;
  const everPublished = lesson?.version != null;
  const status = lesson?.status ?? "draft";
  const changed = Boolean(lesson?.has_unpublished_changes || autosave.dirty);
  const changesToPublish = !everPublished || status === "withdrawn" || changed;
  const stopped = autosave.status === "conflict" || autosave.status === "signed-out";

  const learnerCards = useMemo(() => toLearnerCards(draft.doc, null), [draft.doc]);
  const check = useMemo(() => checkLocally(draft.doc), [draft.doc]);
  const questionCount = cards.filter((card) => card.question).length;

  function edit(change: Partial<Draft>) {
    setDraft((current) => ({ ...current, ...change }));
  }

  function editDoc(change: (doc: Draft["doc"]) => Draft["doc"]) {
    setDraft((current) => ({ ...current, doc: change(current.doc) }));
  }

  function addCard(preset: Preset) {
    const card = newCard(preset);
    editDoc((doc) => insertCard(doc, card, selectedIndex + 1));
    setSelectedId(card.id);
  }

  function duplicate(id: string) {
    const index = cards.findIndex((card) => card.id === id);
    const copy = duplicateCard(cards[index]);
    editDoc((doc) => insertCard(doc, copy, index + 1));
    setSelectedId(copy.id);
  }

  function deleteCard(id: string) {
    const index = cards.findIndex((card) => card.id === id);
    const removed = cards[index];
    editDoc((doc) => removeCard(doc, id));
    const neighbour = cards[index + 1] ?? cards[index - 1];
    setSelectedId(neighbour?.id ?? null);
    setToast({
      message: `Card ${index + 1} deleted.`,
      undo: () => {
        editDoc((doc) => insertCard(doc, removed, index));
        setSelectedId(removed.id);
        setToast(null);
      },
    });
  }

  function goToIssue(issue: Issue) {
    setIssuesShown(null);
    if (issue.card_id && cards.some((card) => card.id === issue.card_id)) {
      setSelectedId(issue.card_id);
    }
  }

  async function loadLatest() {
    if (!lesson) return;
    try {
      const [fresh, freshTopics] = await Promise.all([lessonApi.get(lesson.id), topicApi.list()]);
      latest.current = fresh;
      setLesson(fresh);
      setTopics(freshTopics);
      setDraft(draftOf(fresh));
      setAssets((current) => ({ ...current, ...fresh.assets }));
      adopt(fresh);
      if (!fresh.doc.cards.some((card) => card.id === selectedId)) {
        setSelectedId(fresh.doc.cards[0]?.id ?? null);
      }
    } catch (error) {
      setToast({
        message:
          error instanceof ApiError && error.code === "lesson_not_found"
            ? "This lesson has been deleted."
            : "We couldn't load the latest version. Please try again.",
      });
    }
  }

  /** Publish: save first, then show what blocks it, or ask to confirm. */
  async function startPublish() {
    if (!(await flush())) return;
    const current = latest.current;
    if (!current) return;
    if (current.issues.some((issue) => issue.severity === "blocker")) {
      setIssuesShown(current.issues);
    } else {
      openAction("publish");
    }
  }

  async function startAction(next: Action) {
    if (!(await flush())) return;
    openAction(next);
  }

  function openAction(next: Action) {
    setActionError(null);
    setAction(next);
  }

  async function runAction() {
    const current = latest.current;
    if (!action || !current) return;
    setBusy(true);
    setActionError(null);
    try {
      if (action === "delete") {
        await lessonApi.remove(current);
        allowNavigation();
        const notice: Notice = {
          tone: "success",
          message: `“${lessonTitle(current)}” is deleted.`,
        };
        navigate("/", { state: { notice } });
        return;
      }
      const result = await lessonApi.change(current, action);
      latest.current = result;
      setLesson(result);
      if (action === "discard") setDraft(draftOf(result));
      adopt(result);
      setAction(null);
      // The topic's published count changes with publishing and withdrawing.
      topicApi
        .list()
        .then(setTopics)
        .catch(() => {});
      setToast({
        message: {
          publish: `Published${result.version ? ` as version ${result.version.number}` : ""}. Learners now see it.`,
          discard: "Changes discarded. The draft matches what learners see.",
          withdraw: "Withdrawn. Learners no longer see it; their progress is kept.",
          restore: "Restored. Learners see this lesson again.",
        }[action],
      });
    } catch (error) {
      if (error instanceof ApiError && error.code === "lesson_has_blockers") {
        setAction(null);
        setIssuesShown((error.details.issues as Issue[] | undefined) ?? []);
        return;
      }
      const verb = action === "delete" ? "deleted" : DONE[action];
      setActionError(
        error instanceof ApiError && error.code === "lesson_out_of_date"
          ? `This lesson was changed in another tab or by another administrator, so it wasn't ${verb}. Load the latest version and try again.`
          : error instanceof ApiError
            ? error.message
            : `Something went wrong, so it wasn't ${verb}. Please try again.`,
      );
    } finally {
      setBusy(false);
    }
  }

  const lastInTopic = status === "published" && topic !== null && topic.published_count <= 1;
  const title = lessonTitle(draft);
  const dialogs: Record<Action, { title: string; confirm: string; body: ReactNode }> = {
    publish: {
      title: everPublished
        ? `Publish version ${(lesson?.version?.number ?? 0) + 1}?`
        : `Publish to ${topic?.name ?? "its topic"}?`,
      confirm: everPublished ? "Publish changes" : "Publish",
      body: everPublished ? (
        <p>
          Learners who start or retake this lesson will see the new version. Everyone&rsquo;s
          completions and best scores are kept.
        </p>
      ) : (
        <p>
          Learners will see it in {topic?.name ?? "its topic"}, and it will count toward their
          progress there.
        </p>
      ),
    },
    discard: {
      title: "Discard your changes?",
      confirm: "Discard changes",
      body: (
        <p>
          The draft goes back to version {lesson?.version?.number}, which is what learners see. Your
          changes since then can&rsquo;t be recovered.
        </p>
      ),
    },
    withdraw: {
      title: `Withdraw “${title}”?`,
      confirm: "Withdraw",
      body: (
        <>
          <p>
            Learners will no longer see it. Anyone who completed it keeps their completion and
            score, and it stays in their history. You can restore it at any time.
          </p>
          {lastInTopic && (
            <Alert tone="info">
              This is the last published lesson in {topic?.name}, so the topic will have no content
              left and disappear from learners&rsquo; home page.
            </Alert>
          )}
        </>
      ),
    },
    restore: {
      title: `Restore “${title}”?`,
      confirm: "Restore",
      body: (
        <p>
          Learners will see version {lesson?.version?.number} again.
          {lesson?.has_unpublished_changes && " Your unpublished changes stay in the draft."}
        </p>
      ),
    },
    delete: {
      title: `Delete “${title}”?`,
      confirm: "Delete lesson",
      body: (
        <p>
          This lesson has never been published, so no learner has seen it. Deleting it can&rsquo;t
          be undone.
        </p>
      ),
    },
  };

  const menuItems: MenuAction[] = [];
  if (everPublished && changed) {
    menuItems.push({
      label: "Discard changes",
      icon: RotateCcw,
      onSelect: () => void startAction("discard"),
    });
  }
  if (status === "published") {
    menuItems.push({
      label: "Withdraw",
      icon: EyeOff,
      onSelect: () => void startAction("withdraw"),
    });
  }
  if (status === "withdrawn") {
    menuItems.push({
      label: "Restore",
      icon: ArchiveRestore,
      onSelect: () => void startAction("restore"),
    });
  }
  if (lesson?.deletable) {
    menuItems.push({
      label: "Delete",
      icon: Trash2,
      onSelect: () => void startAction("delete"),
      danger: true,
    });
  }

  const cardIssues = selected ? issues.filter((issue) => issue.card_id === selected.id) : [];
  const titleIssue = issues.find((issue) => issue.code === "missing_title");
  const topicIssue = issues.find((issue) => issue.code === "missing_topic");

  return (
    <div className="flex flex-col gap-4">
      <BackLink />

      {/* The lesson's header: stays at the top while scrolling. */}
      <header className="sticky top-0 z-20 -mx-4 flex flex-col gap-3 border-b border-line bg-surface/95 px-4 py-3 backdrop-blur md:-mx-6 md:px-6 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <LessonDetails
            title={draft.title}
            summary={draft.summary}
            topicId={draft.topic_id}
            topics={topics}
            savedTopicId={lesson?.topic_id ?? null}
            published={everPublished}
            titleError={titleIssue?.message}
            topicError={topicIssue?.message}
            onChange={edit}
          />
        </div>
        <div className="flex shrink-0 flex-col items-start gap-2 lg:items-end">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <StatusBadge status={status} />
            {lesson?.version && (
              <span className="text-caption text-muted">Version {lesson.version.number}</span>
            )}
            {status === "published" && changed && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-2xs font-bold text-amber-800">
                Unpublished changes
              </span>
            )}
            <SaveIndicator status={autosave.status} lesson={lesson} onRetry={() => void flush()} />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="hidden text-xs text-muted xl:inline">
              {lesson ? readingLabel(lesson.stats.reading_seconds) : "Under 1 min"} · {cards.length}{" "}
              {cards.length === 1 ? "card" : "cards"} · {questionCount}{" "}
              {questionCount === 1 ? "question" : "questions"}
            </span>
            <Button variant="secondary" onClick={() => setPreviewOpen(true)}>
              <Eye className="size-4" aria-hidden />
              Preview
            </Button>
            <Button
              onClick={() => void startPublish()}
              disabled={!lesson || stopped || !changesToPublish}
              title={
                blockers.length
                  ? `${blockers.length} thing${blockers.length === 1 ? "" : "s"} to fix first`
                  : undefined
              }
            >
              <Send className="size-4" aria-hidden />
              {!everPublished
                ? "Publish"
                : status === "withdrawn"
                  ? "Publish again"
                  : changesToPublish
                    ? "Publish changes"
                    : "Published"}
              {blockers.length > 0 && (
                <span className="ml-0.5 rounded-full bg-white/20 px-1.5 text-2xs font-bold">
                  {blockers.length}
                </span>
              )}
            </Button>
            {menuItems.length > 0 && (
              <DropdownMenu.Root modal={false}>
                <DropdownMenu.Trigger asChild>
                  <button
                    type="button"
                    aria-label="More actions"
                    className="flex size-10 items-center justify-center rounded-sm text-muted hover:bg-black/5 hover:text-ink data-[state=open]:bg-black/5"
                  >
                    <Ellipsis className="size-5" aria-hidden />
                  </button>
                </DropdownMenu.Trigger>
                <DropdownMenu.Portal>
                  <DropdownMenu.Content
                    align="end"
                    sideOffset={4}
                    className="z-50 min-w-48 rounded-md border border-line bg-white p-1 shadow-lg"
                  >
                    {menuItems.map(({ label, icon: Icon, onSelect, danger }) => (
                      <DropdownMenu.Item
                        key={label}
                        onSelect={onSelect}
                        className={cn(
                          "flex cursor-pointer items-center gap-2 rounded-sm px-2.5 py-2 text-sm outline-none data-[highlighted]:bg-surface",
                          danger ? "text-danger" : "text-ink",
                        )}
                      >
                        <Icon className="size-4" aria-hidden />
                        {label}
                      </DropdownMenu.Item>
                    ))}
                  </DropdownMenu.Content>
                </DropdownMenu.Portal>
              </DropdownMenu.Root>
            )}
          </div>
        </div>
      </header>

      {/* What needs saying about the lesson as a whole. */}
      {stopped && (
        <Alert tone="error">
          <div className="flex flex-col items-start gap-2">
            <p>
              {autosave.status === "signed-out" ? (
                <>
                  You&rsquo;ve been signed out, so your latest changes weren&rsquo;t saved.{" "}
                  <a
                    href="/sign-in"
                    target="_blank"
                    rel="noopener"
                    className="font-semibold underline underline-offset-2"
                  >
                    Sign in again in a new tab
                  </a>
                  , then reload this page.
                </>
              ) : (
                <>
                  {autosave.message} Copy anything you want to keep, then load the latest version.
                </>
              )}
            </p>
            {autosave.status === "conflict" && (
              <Button variant="secondary" size="sm" onClick={() => void loadLatest()}>
                Load the latest version
              </Button>
            )}
          </div>
        </Alert>
      )}
      {autosave.status === "error" && autosave.message && (
        <Alert tone="error">{autosave.message}</Alert>
      )}
      {status === "published" && lesson?.has_unpublished_changes && !stopped && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-900">
          <span className="flex items-center gap-2">
            <CircleAlert className="size-4 shrink-0" aria-hidden />
            Learners see version {lesson.version?.number}. Your changes are a draft until you
            publish them.
          </span>
          <span className="flex gap-2">
            <Button variant="secondary" size="sm" onClick={() => void startAction("discard")}>
              Discard changes
            </Button>
            <Button size="sm" onClick={() => void startPublish()}>
              Publish changes
            </Button>
          </span>
        </div>
      )}
      {status === "withdrawn" && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-line bg-white px-4 py-2.5 text-sm text-muted">
          <span className="flex items-center gap-2">
            <EyeOff className="size-4 shrink-0" aria-hidden />
            Withdrawn: learners don&rsquo;t see this lesson. Their progress in it is kept.
          </span>
          <Button variant="secondary" size="sm" onClick={() => void startAction("restore")}>
            Restore
          </Button>
        </div>
      )}

      {/* The deck, the card being written, and the card as learners will see it. */}
      <div className="grid items-start gap-6 lg:grid-cols-[15rem_minmax(0,1fr)] xl:grid-cols-[15rem_minmax(0,1fr)_23rem]">
        <div className="lg:sticky lg:top-40">
          <CardRail
            cards={cards}
            assets={assets}
            issues={issues}
            selectedId={selected?.id ?? null}
            onSelect={setSelectedId}
            onReorder={(ids) => editDoc((doc) => reorderCards(doc, ids))}
            onAdd={addCard}
            onDuplicate={duplicate}
            onDelete={deleteCard}
          />
        </div>

        <section aria-label="Card" className="min-w-0">
          {selected ? (
            <CardEditor
              key={selected.id}
              card={selected}
              index={selectedIndex}
              total={cards.length}
              assets={assets}
              issues={cardIssues}
              onChange={(change) => editDoc((doc) => updateCard(doc, selected.id, change))}
              onAsset={(asset) => setAssets((current) => ({ ...current, [asset.id]: asset }))}
              onDuplicate={() => duplicate(selected.id)}
              onDelete={() => deleteCard(selected.id)}
            />
          ) : (
            <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-line bg-white p-10 text-center">
              <p className="text-base font-bold text-ink">This lesson has no cards</p>
              <p className="text-sm text-muted">
                A lesson is a deck of short cards, with at least one question.
              </p>
              <Button onClick={() => addCard("story")}>Add the first card</Button>
            </div>
          )}
        </section>

        <aside
          aria-label="Live preview"
          className="sticky top-40 hidden flex-col items-center gap-2 xl:flex"
        >
          <div className="h-[min(720px,calc(100dvh-17rem))] w-full max-w-[22rem] overflow-hidden rounded-[40px] border-[9px] border-ink bg-white shadow-xl">
            <LessonDeck
              variant="embedded"
              lesson={{ title: draft.title, summary: draft.summary, topicName: topic?.name }}
              cards={learnerCards}
              assets={assets}
              check={check}
              index={selectedIndex}
              onIndexChange={(index) => setSelectedId(cards[index]?.id ?? null)}
            />
          </div>
          <p className="text-xs text-muted">Live preview · try the question here</p>
        </aside>
      </div>

      {previewOpen && (
        <LessonPreview
          lesson={{
            title: draft.title,
            summary: draft.summary,
            topicName: topic?.name ?? null,
            readingSeconds: lesson?.stats.reading_seconds,
          }}
          doc={draft.doc}
          assets={assets}
          onClose={() => setPreviewOpen(false)}
        />
      )}

      {action && (
        <ConfirmDialog
          open
          title={dialogs[action].title}
          confirmLabel={dialogs[action].confirm}
          busy={busy}
          error={actionError}
          onConfirm={() => void runAction()}
          onClose={() => setAction(null)}
        >
          {dialogs[action].body}
        </ConfirmDialog>
      )}

      <IssuesDialog
        open={issuesShown !== null}
        issues={issuesShown ?? []}
        cardNumber={(cardId) => {
          const index = cards.findIndex((card) => card.id === cardId);
          return index === -1 ? null : index + 1;
        }}
        onGoTo={goToIssue}
        onClose={() => setIssuesShown(null)}
      />

      <ConfirmDialog
        open={leaveFailed}
        title="Leave without saving?"
        confirmLabel="Leave without saving"
        busy={false}
        error={null}
        onConfirm={() => {
          setLeaveFailed(false);
          blocker.proceed?.();
        }}
        onClose={() => {
          setLeaveFailed(false);
          blocker.reset?.();
        }}
      >
        <p>Your latest changes couldn&rsquo;t be saved. If you leave now, they&rsquo;ll be lost.</p>
      </ConfirmDialog>

      {toast && (
        <div
          role="status"
          className="fixed bottom-6 left-1/2 z-40 flex -translate-x-1/2 items-center gap-3 rounded-full bg-ink py-2.5 pr-2.5 pl-5 text-sm text-white shadow-xl"
        >
          {toast.message}
          {toast.undo ? (
            <button
              type="button"
              onClick={toast.undo}
              className="flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1 font-semibold hover:bg-white/25"
            >
              <Undo2 className="size-4" aria-hidden />
              Undo
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setToast(null)}
              aria-label="Dismiss"
              className="rounded-full px-2 py-1 text-white/70 hover:text-white"
            >
              ✕
            </button>
          )}
        </div>
      )}
    </div>
  );
}
