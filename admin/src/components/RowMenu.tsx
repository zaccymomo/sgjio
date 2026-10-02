import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { cn } from "@sgjio/ui";
import { Ellipsis, type LucideIcon } from "lucide-react";
import { Fragment, useRef } from "react";

export type MenuItem = {
  label: string;
  icon: LucideIcon;
  onSelect: () => void;
  disabled?: boolean;
  /** Destructive, such as Delete. */
  danger?: boolean;
};

/**
 * A row's ⋯ menu: one button that opens a list of actions, so rows show a single control
 * instead of a toolbar. Radix supplies the menu pattern: arrow keys, Home and End, typing
 * a letter, Escape, and focus back on the button when it closes.
 *
 * Items come in groups, drawn with a line between them; empty groups are skipped, and a
 * menu with no items draws nothing. A chosen action runs once focus is back on the button,
 * so a dialog it opens returns focus there too.
 */
export function RowMenu({
  name,
  groups,
  moveKey,
}: {
  /** What the row is, for the button's accessible name: "Actions for Singlish". */
  name: string;
  groups: MenuItem[][];
  /** Marks the button, so focus can follow the row after it moves (see SortableList). */
  moveKey?: string;
}) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const chosen = useRef<(() => void) | null>(null);
  const shown = groups.filter((group) => group.length > 0);
  if (shown.length === 0) return null;

  return (
    // Not modal: the page keeps scrolling, and a press elsewhere just closes the menu.
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger asChild>
        <button
          ref={triggerRef}
          type="button"
          aria-label={`Actions for ${name}`}
          data-move={moveKey}
          className={cn(
            "flex size-9 shrink-0 items-center justify-center rounded-sm text-muted",
            "hover:bg-black/5 hover:text-ink data-[state=open]:bg-black/5 data-[state=open]:text-ink",
            "focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brand",
          )}
        >
          <Ellipsis className="size-4" aria-hidden />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={4}
          collisionPadding={8}
          onCloseAutoFocus={(event) => {
            const action = chosen.current;
            if (!action) return;
            chosen.current = null;
            event.preventDefault();
            triggerRef.current?.focus();
            action();
          }}
          className="z-50 max-w-[calc(100vw-1rem)] min-w-44 rounded-md border border-line bg-white p-1 shadow-lg"
        >
          {shown.map((group, index) => (
            <Fragment key={index}>
              {index > 0 && <DropdownMenu.Separator className="-mx-1 my-1 h-px bg-line" />}
              {group.map(({ label, icon: Icon, onSelect, disabled, danger }) => (
                <DropdownMenu.Item
                  key={label}
                  disabled={disabled}
                  onSelect={() => {
                    chosen.current = onSelect;
                  }}
                  className={cn(
                    "flex cursor-pointer items-center gap-2.5 rounded-sm px-2.5 py-2 text-sm outline-none select-none",
                    "data-highlighted:bg-surface data-disabled:cursor-not-allowed data-disabled:opacity-40",
                    danger ? "text-danger data-highlighted:bg-danger-soft" : "text-ink",
                  )}
                >
                  <Icon className="size-4 shrink-0" aria-hidden />
                  {label}
                </DropdownMenu.Item>
              ))}
            </Fragment>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
