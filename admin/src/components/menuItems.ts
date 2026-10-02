import { ArrowDown, ArrowUp } from "lucide-react";

import type { LessonStatus, LessonSummary } from "../lib/content";
import type { MenuItem } from "./RowMenu";
import type { Reorder } from "./SortableList";

/**
 * What a lesson's ⋯ menu offers, in groups. For now only Move up and Move down. The
 * lesson actions (SCRUM-52, SCRUM-56) go in `byStatus` when they are built:
 *
 * - Draft: Edit, Publish (needs a topic, SCRUM-56), Delete (only drafts can be deleted)
 * - Published: Edit, Withdraw
 * - Withdrawn: Edit, Publish again
 *
 * Move stays its own group in every status, and Delete goes last, in a group of its own.
 */
export function lessonMenuGroups(lesson: LessonSummary, reorder?: Reorder): MenuItem[][] {
  const byStatus: Record<LessonStatus, MenuItem[]> = {
    draft: [],
    published: [],
    withdrawn: [],
  };
  return [byStatus[lesson.status], reorder ? moveItems(reorder) : []];
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
