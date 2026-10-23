import { ArrowDown, ArrowUp, ChartColumn, Pencil, Trash2 } from "lucide-react";

import type { LessonSummary } from "../lib/content";
import type { MenuItem } from "./RowMenu";
import type { Reorder } from "./SortableList";

/**
 * What a lesson's ⋯ menu offers, in groups. Every lesson opens in the editor, whatever its
 * status: editing a published lesson changes its draft, which learners see once published
 * again (SCRUM-52). Publishing, withdrawing and restoring happen in the editor, where the
 * lesson's checks are shown. A lesson that has been published has Insights (SCRUM-84); one
 * never published can be deleted instead.
 *
 * Move stays its own group in every status, and Delete goes last, in a group of its own.
 */
export type LessonActions = {
  edit: (lesson: LessonSummary) => void;
  insights: (lesson: LessonSummary) => void;
  remove: (lesson: LessonSummary) => void;
};

export function lessonMenuGroups(
  lesson: LessonSummary,
  reorder?: Reorder,
  actions?: LessonActions,
): MenuItem[][] {
  const edit = actions
    ? { label: "Edit", icon: Pencil, onSelect: () => actions.edit(lesson) }
    : null;
  const insights =
    actions && lesson.version !== null
      ? { label: "Insights", icon: ChartColumn, onSelect: () => actions.insights(lesson) }
      : null;
  const remove =
    actions && lesson.deletable
      ? {
          label: "Delete",
          icon: Trash2,
          onSelect: () => actions.remove(lesson),
          danger: true,
        }
      : null;
  return [
    [
      ...(edit ? [edit] : []),
      ...(insights ? [insights] : []),
      ...(reorder ? moveItems(reorder) : []),
    ],
    remove ? [remove] : [],
  ];
}

/** Move up and Move down, unavailable at the ends of the list and while reordering is off. */
export function moveItems(reorder: Reorder): MenuItem[] {
  const { moveUp, moveDown, disabled } = reorder;
  return [
    {
      label: "Move up",
      icon: ArrowUp,
      onSelect: () => moveUp?.(),
      disabled: disabled || !moveUp,
    },
    {
      label: "Move down",
      icon: ArrowDown,
      onSelect: () => moveDown?.(),
      disabled: disabled || !moveDown,
    },
  ];
}
