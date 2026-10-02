import {
  closestCenter,
  DndContext,
  DragOverlay,
  KeyboardSensor,
  MouseSensor,
  TouchSensor,
  useSensor,
  useSensors,
  type Announcements,
  type DragEndEvent,
  type DragStartEvent,
  type UniqueIdentifier,
} from "@dnd-kit/core";
import { restrictToVerticalAxis, restrictToWindowEdges } from "@dnd-kit/modifiers";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS as DndCSS } from "@dnd-kit/utilities";
import { cn } from "@sgjio/ui";
import { useEffect, useRef, useState, type ReactNode } from "react";

/** What a row needs to draw its drag handle (DragHandle) and Move up/down menu items. */
export type Reorder = {
  label: string;
  /** Reordering is unavailable: filtering, or a save is running. */
  disabled: boolean;
  handleRef: (element: HTMLElement | null) => void;
  handleProps: Record<string, unknown>;
  /** Undefined at the top of the list. */
  moveUp?: () => void;
  /** Undefined at the bottom of the list. */
  moveDown?: () => void;
  /**
   * Goes on the row's menu button as `data-move`, so focus can follow the row after a
   * move from the menu.
   */
  moveKey: string;
};

const INSTRUCTIONS =
  "To reorder, press Space or Enter to pick up the item, use the up and down arrow keys to " +
  "move it, then press Space or Enter to drop it, or Escape to cancel.";

/**
 * A vertical list whose rows can be reordered by dragging a handle (mouse or touch), by
 * keyboard on the handle, or with Move up and Move down in the row's menu, which are there
 * for anyone who cannot drag (WCAG 2.2, 2.5.7). Every move calls `onReorder` with all ids in the new
 * order and in the order before it, and screen readers hear where the item went.
 *
 * Each list has its own drag context, so a lesson can never be dragged into another topic.
 */
export function SortableList<T>({
  items,
  getId,
  getLabel,
  disabled,
  onReorder,
  onDragChange,
  renderItem,
  renderOverlay,
  className,
  itemClassName,
}: {
  items: T[];
  getId: (item: T) => string;
  getLabel: (item: T) => string;
  disabled: boolean;
  /** All ids in the new order, and in the order shown before the move. */
  onReorder: (ids: string[], previousIds: string[]) => void;
  onDragChange?: (dragging: boolean) => void;
  renderItem: (item: T, reorder: Reorder) => ReactNode;
  /** The compact copy that follows the pointer while dragging. */
  renderOverlay: (item: T) => ReactNode;
  className?: string;
  itemClassName?: string;
}) {
  const ids = items.map(getId);
  const labels = new Map(items.map((item) => [getId(item), getLabel(item)]));
  const [activeId, setActiveId] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const listRef = useRef<HTMLUListElement>(null);
  // After a move from a row's menu, the menu button to put focus back on.
  const pendingFocus = useRef<string | null>(null);

  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 4 } }),
    useSensor(TouchSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  // React may move the focused button's row in the page, which can drop focus; put it back.
  useEffect(() => {
    const key = pendingFocus.current;
    if (!key) return;
    pendingFocus.current = null;
    listRef.current?.querySelector<HTMLElement>(`[data-move="${CSS.escape(key)}"]`)?.focus();
  });

  const label = (id: UniqueIdentifier) => labels.get(String(id)) ?? "Item";
  const place = (id: UniqueIdentifier) =>
    `position ${ids.indexOf(String(id)) + 1} of ${ids.length}`;

  const announcements: Announcements = {
    onDragStart: ({ active }) => `Picked up ${label(active.id)}, at ${place(active.id)}.`,
    onDragOver: ({ active, over }) =>
      over
        ? `${label(active.id)} is now at ${place(over.id)}.`
        : `${label(active.id)} is no longer over the list.`,
    onDragEnd: ({ active, over }) =>
      over
        ? `${label(active.id)} dropped at ${place(over.id)}.`
        : `${label(active.id)} dropped. The order has not changed.`,
    onDragCancel: ({ active }) =>
      `Moving ${label(active.id)} was cancelled. It is back at ${place(active.id)}.`,
  };

  function finishDrag() {
    setActiveId(null);
    onDragChange?.(false);
  }

  function handleDragStart({ active }: DragStartEvent) {
    setActiveId(String(active.id));
    onDragChange?.(true);
  }

  function handleDragEnd({ active, over }: DragEndEvent) {
    finishDrag();
    if (disabled || !over || active.id === over.id) return;
    onReorder(arrayMove(ids, ids.indexOf(String(active.id)), ids.indexOf(String(over.id))), ids);
  }

  function move(index: number, to: number) {
    if (disabled) return;
    const id = ids[index];
    pendingFocus.current = id;
    setAnnouncement(`${label(id)} moved to position ${to + 1} of ${ids.length}.`);
    onReorder(arrayMove(ids, index, to), ids);
  }

  const activeItem = activeId ? items.find((item) => getId(item) === activeId) : undefined;

  return (
    <>
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        modifiers={[restrictToVerticalAxis, restrictToWindowEdges]}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
        onDragCancel={finishDrag}
        accessibility={{ announcements, screenReaderInstructions: { draggable: INSTRUCTIONS } }}
      >
        <SortableContext items={ids} strategy={verticalListSortingStrategy} disabled={disabled}>
          <ul ref={listRef} className={className}>
            {items.map((item, index) => (
              <SortableRow
                key={ids[index]}
                id={ids[index]}
                disabled={disabled}
                className={itemClassName}
              >
                {(handleRef, handleProps) =>
                  renderItem(item, {
                    label: getLabel(item),
                    disabled,
                    handleRef,
                    handleProps,
                    moveUp: index > 0 ? () => move(index, index - 1) : undefined,
                    moveDown: index < items.length - 1 ? () => move(index, index + 1) : undefined,
                    moveKey: ids[index],
                  })
                }
              </SortableRow>
            ))}
          </ul>
        </SortableContext>
        <DragOverlay>{activeItem ? renderOverlay(activeItem) : null}</DragOverlay>
      </DndContext>
      <p className="sr-only" aria-live="polite" aria-atomic>
        {announcement}
      </p>
    </>
  );
}

function SortableRow({
  id,
  disabled,
  className,
  children,
}: {
  id: string;
  disabled: boolean;
  className?: string;
  children: (
    handleRef: (element: HTMLElement | null) => void,
    handleProps: Record<string, unknown>,
  ) => ReactNode;
}) {
  const {
    setNodeRef,
    setActivatorNodeRef,
    attributes,
    listeners,
    transform,
    transition,
    isDragging,
  } = useSortable({ id, disabled });

  return (
    <li
      ref={setNodeRef}
      style={{ transform: DndCSS.Translate.toString(transform), transition }}
      // The row stays in place, faded, while its copy follows the pointer.
      className={cn(className, isDragging && "opacity-40")}
    >
      {children(setActivatorNodeRef, { ...attributes, ...listeners })}
    </li>
  );
}
