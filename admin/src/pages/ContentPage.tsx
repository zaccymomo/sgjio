import { Alert, ApiError, Button, ErrorState, Spinner, cn } from "@sgjio/ui";
import { ChevronRight, GripVertical, Plus, X } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { ContentToolbar, type View } from "../components/ContentToolbar";
import { ConfirmLessonDeleteDialog } from "../components/LessonDialogs";
import { LessonRow } from "../components/LessonRow";
import { lessonMenuGroups, type LessonActions } from "../components/menuItems";
import { RowMenu } from "../components/RowMenu";
import { SortableList } from "../components/SortableList";
import {
  ConfirmTopicDialog,
  TopicNameDialog,
  type ConfirmState,
  type NameDialogState,
} from "../components/TopicDialogs";
import { TopicGroup, type TopicActions } from "../components/TopicGroup";
import {
  topicApi,
  useContent,
  type Content,
  type LessonSummary,
  type Notice,
  type Topic,
} from "../lib/content";
import {
  lessonTitle,
  NO_FILTERS,
  viewContent,
  type ContentView,
  type Filters,
} from "../lib/filter";
import { plural, topicSummary } from "../lib/format";
import { lessonApi } from "../lib/lessons";

const VIEW_KEY = "sgjio-admin-content-view";
const NO_TOPIC = "none";
const ARCHIVED = "archived";

// Remembered per browser. Storage can be unavailable (private windows, blocked site
// data), in which case the page simply opens in topic order.
function readView(): View {
  try {
    return localStorage.getItem(VIEW_KEY) === "recent" ? "recent" : "topics";
  } catch {
    return "topics";
  }
}

function rememberView(view: View) {
  try {
    localStorage.setItem(VIEW_KEY, view);
  } catch {
    // Not remembered; nothing else depends on it.
  }
}

function messageOf(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

/**
 * The admin portal's landing page (SCRUM-66): every topic, in the order users see their
 * circles, each opening to its lessons in order. Topics and lessons are reordered here,
 * and topics are created, renamed, archived, restored and deleted (SCRUM-57).
 */
export function ContentPage() {
  const location = useLocation();
  const navigate = useNavigate();
  // A message the lesson editor sent along, e.g. after deleting a draft.
  const [passedNotice] = useState(
    () => (location.state as { notice?: Notice } | null)?.notice ?? null,
  );
  const content = useContent(passedNotice);
  const { state, notice, setNotice, retry } = content;
  const [view, setView] = useState<View>(readView);
  const [nameDialog, setNameDialog] = useState<NameDialogState | null>(null);
  const [confirm, setConfirm] = useState<ConfirmState | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [lessonToDelete, setLessonToDelete] = useState<LessonSummary | null>(null);
  const [lessonDeleteBusy, setLessonDeleteBusy] = useState(false);
  const [lessonDeleteError, setLessonDeleteError] = useState<string | null>(null);
  const [busyTopicId, setBusyTopicId] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  // After archiving, deleting or restoring, the button that was used has gone; put focus
  // somewhere sensible once the dialog has closed.
  const focusHeadingNext = useRef(false);

  useEffect(() => {
    if (focusHeadingNext.current) {
      focusHeadingNext.current = false;
      headingRef.current?.focus();
    }
  });

  // Shown once: clear it from history, so going back or reloading does not show it again.
  useEffect(() => {
    if ((location.state as { notice?: Notice } | null)?.notice) {
      navigate(location.pathname + location.search, { replace: true, state: null });
    }
  }, [location, navigate]);

  // Success messages clear themselves; errors stay until dismissed or replaced.
  useEffect(() => {
    if (notice?.tone !== "success") return;
    const timer = window.setTimeout(() => setNotice(null), 6000);
    return () => window.clearTimeout(timer);
  }, [notice, setNotice]);

  const data = state.status === "ready" ? state.content : null;
  // The dialog shows the topic as it is now, so counts are fresh after a refresh.
  const confirmTopic = confirm
    ? (data?.topics.find((topic) => topic.id === confirm.topic.id) ?? confirm.topic)
    : null;

  function openConfirm(kind: ConfirmState["kind"], topic: Topic) {
    setConfirmError(null);
    setConfirm({ kind, topic });
  }

  async function confirmAction() {
    if (!confirm) return;
    const topic = confirmTopic ?? confirm.topic;
    setConfirmBusy(true);
    setConfirmError(null);
    try {
      if (confirm.kind === "archive") {
        await content.run(() => topicApi.archive(topic.id));
        setNotice({
          tone: "success",
          message: `“${topic.name}” is archived. Users no longer see it.`,
        });
      } else {
        await content.run(() => topicApi.remove(topic.id));
        setNotice({ tone: "success", message: `“${topic.name}” is deleted.` });
      }
      focusHeadingNext.current = true;
      setConfirm(null);
    } catch (error) {
      if (error instanceof ApiError && error.code === "topic_not_empty") {
        // A lesson was added since the page loaded, so offer what the server will allow.
        setConfirm({
          kind: "archive",
          topic,
          reason:
            "A lesson has been added to this topic since you loaded the page, so it can't " +
            "be deleted. You can archive it instead.",
        });
      } else if (error instanceof ApiError && error.code === "topic_not_found") {
        setConfirm(null);
        setNotice({
          tone: "info",
          message: "That topic no longer exists. The list is up to date.",
        });
      } else {
        setConfirmError(messageOf(error, "Something went wrong. Please try again."));
      }
    } finally {
      setConfirmBusy(false);
    }
  }

  async function saveName(name: string) {
    if (!nameDialog) return;
    if (nameDialog.mode === "create") {
      await content.run(() => topicApi.create(name));
      setNotice({ tone: "success", message: `“${name}” is created, at the end of the list.` });
    } else {
      const saved = await content.run(() => topicApi.rename(nameDialog.topic.id, name));
      setNotice({ tone: "success", message: `Renamed to “${saved.name}”.` });
    }
    setNameDialog(null);
  }

  async function deleteLesson() {
    if (!lessonToDelete) return;
    const lesson = data?.lessons.find(({ id }) => id === lessonToDelete.id) ?? lessonToDelete;
    setLessonDeleteBusy(true);
    setLessonDeleteError(null);
    try {
      await content.run(() => lessonApi.remove(lesson));
      setNotice({ tone: "success", message: `“${lessonTitle(lesson)}” is deleted.` });
      focusHeadingNext.current = true;
      setLessonToDelete(null);
    } catch (error) {
      if (error instanceof ApiError && error.code === "lesson_not_found") {
        setLessonToDelete(null);
        setNotice({ tone: "info", message: "That lesson had already been deleted." });
      } else if (error instanceof ApiError && error.code === "lesson_not_deletable") {
        setLessonToDelete(null);
        setNotice({
          tone: "info",
          message: "That lesson has been published, so it can't be deleted.",
        });
      } else if (error instanceof ApiError && error.code === "lesson_out_of_date") {
        setLessonToDelete(null);
        setNotice({
          tone: "info",
          message:
            "That draft changed since you opened the list. Open it and check it before deleting.",
        });
      } else {
        setLessonDeleteError(messageOf(error, "Something went wrong. Please try again."));
      }
    } finally {
      setLessonDeleteBusy(false);
    }
  }

  async function restore(topic: Topic) {
    setBusyTopicId(topic.id);
    try {
      await content.run(() => topicApi.restore(topic.id));
      setNotice({
        tone: "success",
        message: `“${topic.name}” is visible to users again, at the end of your topic list.`,
      });
      focusHeadingNext.current = true;
    } catch (error) {
      setNotice({ tone: "error", message: messageOf(error, "The topic wasn't restored.") });
    } finally {
      setBusyTopicId(null);
    }
  }

  const actions: TopicActions = {
    rename: (topic) => setNameDialog({ mode: "rename", topic }),
    archive: (topic) => openConfirm("archive", topic),
    remove: (topic) => openConfirm("delete", topic),
    restore: (topic) => void restore(topic),
    addLesson: (topic) => navigate(`/lessons/new?${new URLSearchParams({ topic: topic.id })}`),
  };
  const lessonActions: LessonActions = {
    edit: (lesson) => navigate(`/lessons/${lesson.id}`),
    remove: (lesson) => {
      setLessonDeleteError(null);
      setLessonToDelete(lesson);
    },
  };

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 ref={headingRef} tabIndex={-1} className="text-2xl font-bold text-ink outline-none">
            Content
          </h1>
          <p className="mt-1 text-sm text-muted">
            Topics appear as progress circles on users&rsquo; home page, in the order shown here.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            className="flex-1 sm:flex-none"
            onClick={() => setNameDialog({ mode: "create" })}
            disabled={!data}
          >
            <Plus className="size-4" aria-hidden />
            New topic
          </Button>
          <Button className="flex-1 sm:flex-none" onClick={() => navigate("/lessons/new")}>
            <Plus className="size-4" aria-hidden />
            New lesson
          </Button>
        </div>
      </div>

      {state.status === "loading" && (
        <div className="flex justify-center py-16 text-brand">
          <Spinner className="size-6" label="Loading topics and lessons" />
        </div>
      )}

      {/* SCRUM-66 AC7 */}
      {state.status === "error" && <ErrorState message={state.message} onRetry={retry} />}

      {data && (
        <ContentBody
          data={data}
          view={view}
          onViewChange={(next) => {
            setView(next);
            rememberView(next);
          }}
          content={content}
          actions={actions}
          lessonActions={lessonActions}
          busyTopicId={busyTopicId}
          onCreateTopic={() => setNameDialog({ mode: "create" })}
          notice={notice}
          onDismissNotice={() => setNotice(null)}
        />
      )}

      <TopicNameDialog state={nameDialog} onClose={() => setNameDialog(null)} onSave={saveName} />
      <ConfirmTopicDialog
        state={confirm && confirmTopic ? { ...confirm, topic: confirmTopic } : null}
        busy={confirmBusy}
        error={confirmError}
        onCancel={() => setConfirm(null)}
        onConfirm={() => void confirmAction()}
      />
      <ConfirmLessonDeleteDialog
        lesson={lessonToDelete}
        busy={lessonDeleteBusy}
        error={lessonDeleteError}
        onCancel={() => setLessonToDelete(null)}
        onConfirm={() => void deleteLesson()}
      />
    </div>
  );
}

function ContentBody({
  data,
  view,
  onViewChange,
  content,
  actions,
  lessonActions,
  busyTopicId,
  onCreateTopic,
  notice,
  onDismissNotice,
}: {
  data: Content;
  view: View;
  onViewChange: (view: View) => void;
  content: ReturnType<typeof useContent>;
  actions: TopicActions;
  lessonActions: LessonActions;
  busyTopicId: string | null;
  onCreateTopic: () => void;
  notice: Notice | null;
  onDismissNotice: () => void;
}) {
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  // A topic filter can point at a topic that has since been deleted; treat that as "all".
  const effectiveFilters = useMemo(() => {
    const known =
      filters.topic === "all" ||
      filters.topic === NO_TOPIC ||
      data.topics.some((topic) => topic.id === filters.topic);
    return known ? filters : { ...filters, topic: "all" };
  }, [filters, data.topics]);
  const contentView = useMemo(
    () => viewContent(data.topics, data.lessons, effectiveFilters),
    [data, effectiveFilters],
  );
  const { filtering } = contentView;
  const expansion = useExpansion(filtering, JSON.stringify(effectiveFilters));

  if (data.topics.length === 0 && data.lessons.length === 0) {
    return (
      <EmptyCard title="No topics yet">
        <p>
          Topics group lessons, and each one appears as a progress circle on users&rsquo; home page.
          Create your first topic to get started.
        </p>
        <Button variant="secondary" onClick={onCreateTopic} className="mt-1 self-center">
          <Plus className="size-4" aria-hidden />
          New topic
        </Button>
      </EmptyCard>
    );
  }

  const result = filtering ? resultText(contentView, view) : "";

  return (
    <>
      <ContentToolbar
        filters={effectiveFilters}
        onFiltersChange={setFilters}
        filtering={filtering}
        view={view}
        onViewChange={onViewChange}
        topics={data.topics}
        hasLessonsWithoutTopic={data.lessons.some((lesson) => lesson.topic_id === null)}
        result={result}
      />

      {/* Always present, so messages are announced; takes no space when empty. */}
      <div aria-live="polite" aria-atomic className="empty:-mt-5">
        {notice && (
          <div className="relative">
            <Alert tone={notice.tone} className="pr-10">
              {notice.message}
            </Alert>
            <button
              type="button"
              onClick={onDismissNotice}
              aria-label="Dismiss message"
              className="absolute top-1.5 right-1.5 flex size-7 items-center justify-center rounded-sm text-muted hover:bg-black/5 focus-visible:outline-2 focus-visible:outline-brand"
            >
              <X className="size-3.5" aria-hidden />
            </button>
          </div>
        )}
      </div>

      {view === "recent" ? (
        <RecentList
          contentView={contentView}
          topics={data.topics}
          lessonActions={lessonActions}
          filtering={filtering}
          onClear={() => setFilters(NO_FILTERS)}
        />
      ) : (
        <TopicOrder
          contentView={contentView}
          content={content}
          actions={actions}
          lessonActions={lessonActions}
          busyTopicId={busyTopicId}
          expansion={expansion}
          onClear={() => setFilters(NO_FILTERS)}
          query={effectiveFilters.query.trim()}
        />
      )}
    </>
  );
}

/** "3 lessons in 2 topics", or "4 lessons found" in the flat list. */
function resultText(contentView: ContentView, view: View): string {
  if (view === "recent") return `${plural(contentView.recent.length, "lesson")} found`;
  const topics = contentView.active.length + contentView.archived.length;
  const where = [topics > 0 && plural(topics, "topic"), contentView.noTopic && "No topic"]
    .filter(Boolean)
    .join(" and ");
  return `${plural(contentView.lessonCount, "lesson")}${where ? ` in ${where}` : ""}`;
}

type Expansion = ReturnType<typeof useExpansion>;

/**
 * Which topics are open. Without filters, only the ones the administrator opened (all
 * closed at first). While searching or filtering, every group shown is open, so matching
 * lessons are visible, but can still be closed; clearing the filters goes back to how it
 * was.
 */
function useExpansion(filtering: boolean, filtersKey: string) {
  const [opened, setOpened] = useState<Set<string>>(() => new Set());
  const [closedWhileFiltering, setClosedWhileFiltering] = useState({
    key: "",
    ids: new Set<string>(),
  });
  const closed =
    closedWhileFiltering.key === filtersKey ? closedWhileFiltering.ids : new Set<string>();

  const isOpen = (id: string) => (filtering ? !closed.has(id) : opened.has(id));

  function setOpen(ids: string[], open: boolean) {
    const change = (set: Set<string>, add: boolean) => {
      const next = new Set(set);
      for (const id of ids) {
        if (add) next.add(id);
        else next.delete(id);
      }
      return next;
    };
    if (filtering) {
      setClosedWhileFiltering((previous) => ({
        key: filtersKey,
        ids: change(previous.key === filtersKey ? previous.ids : new Set(), !open),
      }));
    } else {
      setOpened((previous) => change(previous, open));
    }
  }

  return { isOpen, setOpen, toggle: (id: string) => setOpen([id], !isOpen(id)) };
}

function TopicOrder({
  contentView,
  content,
  actions,
  lessonActions,
  busyTopicId,
  expansion,
  onClear,
  query,
}: {
  contentView: ContentView;
  content: ReturnType<typeof useContent>;
  actions: TopicActions;
  lessonActions: LessonActions;
  busyTopicId: string | null;
  expansion: Expansion;
  onClear: () => void;
  query: string;
}) {
  const { active, noTopic, archived, filtering } = contentView;
  const { saving, reorderTopics, reorderLessons, setDragging } = content;
  const archivedPanelId = useId();
  // Reordering needs the whole list, which a search or filter hides part of.
  const reorderDisabled = saving || filtering;

  if (filtering && active.length === 0 && !noTopic && archived.length === 0) {
    return <NoMatches query={query} onClear={onClear} />;
  }

  const groupIds = [...active.map(({ topic }) => topic!.id), ...(noTopic ? [NO_TOPIC] : [])];
  const anyOpen = groupIds.some(expansion.isOpen);

  const lessonReorder = (topicId: string | null) => ({
    disabled: reorderDisabled,
    onReorder: (ids: string[], previousIds: string[]) => reorderLessons(topicId, ids, previousIds),
    onDragChange: setDragging,
  });

  return (
    <div className="flex flex-col gap-3">
      {filtering && (
        <Alert tone="info">
          <span>Reordering is off while you search or filter. </span>
          <button
            type="button"
            onClick={onClear}
            className="font-semibold text-ink underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-brand"
          >
            Clear filters to reorder
          </button>
        </Alert>
      )}

      <div className="flex min-h-8 items-center justify-between gap-2">
        <h2 className="text-caption font-semibold tracking-wide text-muted uppercase">Topics</h2>
        <div className="flex items-center gap-3">
          {saving && (
            <span className="flex items-center gap-1.5 text-caption text-muted">
              <Spinner className="size-3" label="Saving" />
              Saving order…
            </span>
          )}
          {groupIds.length > 0 && (
            <Button variant="ghost" size="sm" onClick={() => expansion.setOpen(groupIds, !anyOpen)}>
              {anyOpen ? "Collapse all" : "Expand all"}
            </Button>
          )}
        </div>
      </div>

      {active.length === 0 && !filtering && (
        <EmptyCard title="No active topics">
          <p>Every topic is archived. Create a topic, or restore one from Archived topics below.</p>
        </EmptyCard>
      )}

      {active.length > 0 && (
        <SortableList
          items={active}
          getId={({ topic }) => topic!.id}
          getLabel={({ topic }) => topic!.name}
          disabled={reorderDisabled}
          onReorder={reorderTopics}
          onDragChange={setDragging}
          className="flex flex-col gap-2"
          renderItem={(group, reorder) => (
            <TopicGroup
              group={group}
              expanded={expansion.isOpen(group.topic!.id)}
              onToggle={() => expansion.toggle(group.topic!.id)}
              reorder={reorder}
              lessonReorder={lessonReorder(group.topic!.id)}
              actions={actions}
              lessonActions={lessonActions}
              busy={busyTopicId === group.topic!.id}
            />
          )}
          renderOverlay={({ topic }) => <TopicOverlay topic={topic!} />}
        />
      )}

      {/* Pinned below the topics: it is not a topic, so it is never dragged. */}
      {noTopic && (
        <TopicGroup
          group={noTopic}
          expanded={expansion.isOpen(NO_TOPIC)}
          onToggle={() => expansion.toggle(NO_TOPIC)}
          lessonReorder={lessonReorder(null)}
          lessonActions={lessonActions}
        />
      )}

      {archived.length > 0 && (
        <section className="mt-3 flex flex-col gap-2">
          <button
            type="button"
            aria-expanded={expansion.isOpen(ARCHIVED)}
            aria-controls={archivedPanelId}
            onClick={() => expansion.toggle(ARCHIVED)}
            className="flex w-fit items-center gap-1.5 rounded-sm text-sm font-semibold text-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          >
            <ChevronRight
              className={cn(
                "size-4 transition-transform",
                expansion.isOpen(ARCHIVED) && "rotate-90",
              )}
              aria-hidden
            />
            Archived topics ({archived.length})
          </button>
          {expansion.isOpen(ARCHIVED) && (
            <div id={archivedPanelId} className="flex flex-col gap-2">
              <p className="text-caption text-muted">
                Hidden from users, with their lessons and progress kept. A restored topic goes to
                the end of the list.
              </p>
              <ul className="flex flex-col gap-2">
                {archived.map((group) => (
                  <li key={group.topic!.id}>
                    <TopicGroup
                      group={group}
                      expanded={expansion.isOpen(group.topic!.id)}
                      onToggle={() => expansion.toggle(group.topic!.id)}
                      actions={actions}
                      lessonActions={lessonActions}
                      busy={busyTopicId === group.topic!.id}
                    />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function RecentList({
  contentView,
  topics,
  lessonActions,
  filtering,
  onClear,
}: {
  contentView: ContentView;
  topics: Topic[];
  lessonActions: LessonActions;
  filtering: boolean;
  onClear: () => void;
}) {
  const { recent } = contentView;
  const byId = new Map(topics.map((topic) => [topic.id, topic]));

  if (recent.length === 0) {
    return filtering ? (
      <NoMatches query="" onClear={onClear} />
    ) : (
      // SCRUM-66 AC6
      <EmptyCard title="No lessons yet">
        <p>Create one with New lesson.</p>
      </EmptyCard>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <h2 className="text-caption font-semibold tracking-wide text-muted uppercase">
        Most recently updated first
      </h2>
      <ul className="divide-y divide-line rounded-lg border border-line bg-white">
        {recent.map((lesson) => {
          const topic = lesson.topic_id ? byId.get(lesson.topic_id) : undefined;
          const topicLabel = topic
            ? `${topic.name}${topic.archived_at ? " (archived)" : ""}`
            : "No topic";
          return (
            <li key={lesson.id}>
              <LessonRow
                lesson={lesson}
                topicLabel={topicLabel}
                menu={
                  <RowMenu
                    name={lessonTitle(lesson)}
                    groups={lessonMenuGroups(lesson, undefined, lessonActions)}
                  />
                }
              />
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function TopicOverlay({ topic }: { topic: Topic }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-line bg-white px-3 py-3 shadow-lg">
      <GripVertical className="size-4 text-subtle" aria-hidden />
      <span className="text-sm font-semibold text-ink">{topic.name}</span>
      <span className="text-caption text-muted">{topicSummary(topic)}</span>
    </div>
  );
}

function EmptyCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-1 rounded-lg border border-line bg-surface p-6 text-center text-sm text-muted">
      <h2 className="text-sm font-semibold text-ink">{title}</h2>
      {children}
    </section>
  );
}

function NoMatches({ query, onClear }: { query: string; onClear: () => void }) {
  return (
    <EmptyCard title={query ? `Nothing matches “${query}”` : "Nothing matches these filters"}>
      <p>Try a different search, or clear the filters to see everything.</p>
      <Button variant="secondary" onClick={onClear} className="mt-2 self-center">
        Clear filters
      </Button>
    </EmptyCard>
  );
}
