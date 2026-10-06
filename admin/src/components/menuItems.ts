import { ArrowDown, ArrowUp, Pencil, Trash2 } from "lucide-react";

import type { LessonSummary } from "../lib/content";
import type { MenuItem } from "./RowMenu";
import type { Reorder } from "./SortableList";

/**
 * What a lesson's ⋯ menu offers, in groups. Drafts can be opened in the editor and, if they
 * have never been published, deleted. Publishing and withdrawing arrive with SCRUM-52 and
 * SCRUM-56:
 *
 * - Draft: Edit, Publish (needs a topic, SCRUM-56), Delete (only drafts can be deleted)
 * - Published: Edit, Withdraw
 * - Withdrawn: Edit, Publish again
 *
 * Move stays its own group in every status, and Delete goes last, in a group of its own.
 */
export type LessonActions = {
  edit: (lesson: LessonSummary) => void;
  remove: (lesson: LessonSummary) => void;
};

export function lessonMenuGroups(
  lesson: LessonSummary,
  reorder?: Reorder,
  actions?: LessonActions,
): MenuItem[][] {
  const edit =
    actions && lesson.status === "draft"
      ? { label: "Edit", icon: Pencil, onSelect: () => actions.edit(lesson) }
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
    [...(edit ? [edit] : []), ...(reorder ? moveItems(reorder) : [])],
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
