import { cn } from "@sgjio/ui";
import { GripVertical } from "lucide-react";

import type { Reorder } from "./SortableList";

/**
 * The drag handle. Only the handle starts a drag (mouse, touch, or Space and the arrow keys),
 * and only the handle blocks touch scrolling, so the page still scrolls when a finger lands
 * on a row. Move up and Move down live in the row's ⋯ menu.
 */
export function DragHandle({ reorder }: { reorder: Reorder }) {
  const { label, disabled, handleRef, handleProps } = reorder;

  return (
    <button
      type="button"
      ref={handleRef}
      {...handleProps}
      aria-label={`Reorder ${label}`}
      // aria-disabled rather than disabled, so the handle keeps focus while a save runs.
      aria-disabled={disabled || undefined}
      className={cn(
        "flex h-10 w-8 shrink-0 touch-none items-center justify-center rounded-sm text-subtle",
        "cursor-grab hover:bg-black/5 hover:text-ink active:cursor-grabbing",
        "focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brand",
        "aria-disabled:cursor-not-allowed aria-disabled:opacity-35",
      )}
    >
      <GripVertical className="size-4" aria-hidden />
    </button>
  );
}
