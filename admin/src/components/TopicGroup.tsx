import { cn } from "@sgjio/ui";
import {
  Archive,
  ArchiveRestore,
  ChevronRight,
  FilePlus,
  FileText,
  Pencil,
  Trash2,
} from "lucide-react";
import { useId } from "react";

import type { LessonSummary, Topic } from "../lib/content";
import { lessonTitle, type Group } from "../lib/filter";
import { formatDate, plural, topicSummary } from "../lib/format";
import { LEVEL_DESCRIPTIONS, LEVELS, levelLabel } from "../lib/levels";
import { DragHandle } from "./DragHandle";
import { LessonRow } from "./LessonRow";
import { lessonMenuGroups, moveItems, type LessonActions } from "./menuItems";
import { RowMenu, type MenuItem } from "./RowMenu";
import { SortableList, type Reorder } from "./SortableList";

export type TopicActions = {
  /** Open the Edit topic dialog, with the cursor in the description if `focus` says so. */
  edit: (topic: Topic, focus?: "description") => void;
  archive: (topic: Topic) => void;
  remove: (topic: Topic) => void;
  restore: (topic: Topic) => void;
  /** Open the lesson editor with this topic chosen (SCRUM-64). */
  addLesson: (topic: Topic) => void;
};

/** Takes the drag handle's place where there is none, so names and titles line up. */
const handleSpace = <span className="w-8 shrink-0" aria-hidden />;

/**
 * A topic as a collapsible row: a white header, which opens to show its description
 * (SCRUM-86) and its lessons, in order, on a grey panel and indented, so they read as
 * belonging to it. Every row has a drag
 * handle and a ⋯ menu, which holds the topic's actions and Move up and Move down.
 *
 * Also used for the lessons with no topic (`group.topic` is null: no name to edit, never
 * dragged) and for archived topics (no reordering, and Restore instead of Archive).
 */
export function TopicGroup({
  group,
  expanded,
  onToggle,
  reorder,
  lessonReorder,
  actions,
  lessonActions,
  busy,
}: {
  group: Group;
  expanded: boolean;
  onToggle: () => void;
  /** How the topic itself is reordered. Absent for the no-topic group and archived topics. */
  reorder?: Reorder;
  /** How its lessons are reordered. Absent when they cannot be (archived topics). */
  lessonReorder?: {
    disabled: boolean;
    onReorder: (ids: string[], previousIds: string[]) => void;
    onDragChange: (dragging: boolean) => void;
  };
  actions?: TopicActions;
  lessonActions?: LessonActions;
  /** A change to this topic is running. */
  busy?: boolean;
}) {
  const panelId = useId();
  const { topic, lessons, allLessons } = group;
  const name = topic?.name ?? "No topic";
  const archived = topic?.archived_at != null;

  const meta = topic
    ? [archived && `Archived ${formatDate(topic.archived_at!)}`, topicSummary(topic)]
        .filter(Boolean)
        .join(" · ")
    : `Drafts not yet in a topic · ${plural(allLessons.length, "lesson")}`;
  // So a collapsed topic still says it has problems to look at (SCRUM-83 AC4).
  const openReports = allLessons.reduce((total, lesson) => total + lesson.open_reports, 0);

  return (
    <div
      className={cn(
        "overflow-hidden rounded-lg border border-line bg-white",
        archived && "border-dashed",
      )}
    >
      <div className="flex items-center gap-1 p-1">
        {reorder ? <DragHandle reorder={reorder} /> : handleSpace}
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={expanded}
          aria-controls={panelId}
          className={cn(
            "flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-2 text-left hover:bg-surface",
            "focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brand",
          )}
        >
          <ChevronRight
            className={cn(
              "size-4 shrink-0 text-muted transition-transform",
              expanded && "rotate-90",
            )}
            aria-hidden
          />
          <span className="flex min-w-0 flex-1 flex-col gap-x-4 sm:flex-row sm:items-center sm:justify-between">
            <span
              className={cn(
                "text-sm font-semibold break-words",
                topic && !archived ? "text-ink" : "text-muted",
              )}
            >
              {name}
            </span>
            <span className="shrink-0 text-caption text-muted">
              {meta}
              {openReports > 0 && (
                <span className="font-semibold text-danger">
                  {" "}
                  · {plural(openReports, "open report")}
                </span>
              )}
            </span>
          </span>
        </button>
        {topic && actions && (
          <RowMenu
            name={name}
            groups={topicMenuGroups(topic, actions, reorder, busy)}
            moveKey={reorder?.moveKey}
          />
        )}
      </div>

      {expanded && (
        <div id={panelId} className="border-t border-line bg-surface">
          {topic && (
            <TopicDescription
              topic={topic}
              onAdd={actions && (() => actions.edit(topic, "description"))}
            />
          )}
          {topic && <LevelCounts topic={topic} />}
          {allLessons.length === 0 ? (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 py-3 pr-4 pl-12 text-sm text-muted">
              <p>No lessons in this topic yet.</p>
              {topic && !archived && actions && (
                <button
                  type="button"
                  onClick={() => actions.addLesson(topic)}
                  className="rounded-sm font-semibold text-ink underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-brand"
                >
                  Add a lesson
                </button>
              )}
            </div>
          ) : (
            <>
              {lessons.length < allLessons.length && (
                <p className="pt-2 pr-4 pl-12 text-caption text-muted">
                  Showing {lessons.length} of {plural(allLessons.length, "lesson")}
                </p>
              )}
              {lessonReorder ? (
                <SortableList
                  items={lessons}
                  getId={(lesson) => lesson.id}
                  getLabel={lessonTitle}
                  disabled={lessonReorder.disabled}
                  onReorder={lessonReorder.onReorder}
                  onDragChange={lessonReorder.onDragChange}
                  className={lessonListClass}
                  itemClassName="bg-surface"
                  renderItem={(lesson, lessonControls) => (
                    <LessonRow
                      lesson={lesson}
                      handle={<DragHandle reorder={lessonControls} />}
                      menu={
                        <RowMenu
                          name={lessonTitle(lesson)}
                          groups={lessonMenuGroups(lesson, lessonControls, lessonActions)}
                          moveKey={lessonControls.moveKey}
                        />
                      }
                    />
                  )}
                  renderOverlay={(lesson) => <LessonOverlay lesson={lesson} />}
                />
              ) : (
                <ul className={lessonListClass}>
                  {lessons.map((lesson) => (
                    <li key={lesson.id}>
                      <LessonRow
                        lesson={lesson}
                        handle={handleSpace}
                        menu={
                          <RowMenu
                            name={lessonTitle(lesson)}
                            groups={lessonMenuGroups(lesson, undefined, lessonActions)}
                          />
                        }
                      />
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

// Indented so lesson titles begin to the right of the topic's name, with dividers that start
// there too. On desktop each lesson's handle sits under the topic's chevron; on a phone the
// indent is smaller, to leave room for the title.
const lessonListClass = "ml-4 divide-y divide-line sm:ml-10";

/**
 * Add lesson, Edit, Move up, Move down, then Archive, or Delete while the topic has no
 * lessons. An archived topic offers Edit, Restore, and Delete if it is empty.
 */
function topicMenuGroups(
  topic: Topic,
  actions: TopicActions,
  reorder: Reorder | undefined,
  busy: boolean | undefined,
): MenuItem[][] {
  const empty = topic.lesson_count === 0;
  const edit: MenuItem = {
    label: "Edit",
    icon: Pencil,
    onSelect: () => actions.edit(topic),
    disabled: busy,
  };
  const remove: MenuItem = {
    label: "Delete",
    icon: Trash2,
    onSelect: () => actions.remove(topic),
    disabled: busy,
    danger: true,
  };

  if (topic.archived_at !== null) {
    const restore: MenuItem = {
      label: "Restore",
      icon: ArchiveRestore,
      onSelect: () => actions.restore(topic),
      disabled: busy,
    };
    return [[edit, restore], empty ? [remove] : []];
  }

  const addLesson: MenuItem = {
    label: "Add lesson",
    icon: FilePlus,
    onSelect: () => actions.addLesson(topic),
    disabled: busy,
  };
  const archive: MenuItem = {
    label: "Archive",
    icon: Archive,
    onSelect: () => actions.archive(topic),
    disabled: busy,
  };
  return [[addLesson, edit, ...(reorder ? moveItems(reorder) : [])], [empty ? remove : archive]];
}

/**
 * What users read under the topic's name on its page, so administrators can see it without
 * opening the dialog. With none, a link opens the dialog at the description.
 */
function TopicDescription({ topic, onAdd }: { topic: Topic; onAdd?: () => void }) {
  if (topic.description) {
    return <p className="pt-3 pr-4 pb-1 pl-12 text-sm text-muted">{topic.description}</p>;
  }
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-3 pr-4 pb-1 pl-12 text-sm text-subtle">
      <p>No description yet.</p>
      {onAdd && (
        <button
          type="button"
          onClick={onAdd}
          className="rounded-sm font-semibold text-ink underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-brand"
        >
          Add a description
        </button>
      )}
    </div>
  );
}

/**
 * Published lessons at each level (SCRUM-103 AC5). Zeros are shown too: a level with
 * nothing published is a gap the aptitude quiz can exempt learners across.
 */
function LevelCounts({ topic }: { topic: Topic }) {
  return (
    <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1 pt-2 pr-4 pb-1 pl-12 text-caption text-muted">
      <span className="font-semibold">Published by level:</span>
      <ul className="flex flex-wrap gap-1.5">
        {LEVELS.map((level, index) => {
          const count = topic.published_by_level[index] ?? 0;
          return (
            <li
              key={level}
              title={LEVEL_DESCRIPTIONS[level]}
              className={cn(
                "rounded-full px-2 py-px",
                count > 0 ? "bg-white font-semibold text-ink ring-1 ring-line" : "text-subtle",
              )}
            >
              {levelLabel(level)}: {count}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function LessonOverlay({ lesson }: { lesson: LessonSummary }) {
  return (
    <div className="flex items-center gap-2.5 rounded-md border border-line bg-white px-4 py-3 text-sm text-ink shadow-lg">
      <FileText className="size-4 shrink-0 text-subtle" aria-hidden />
      {lessonTitle(lesson)}
    </div>
  );
}
