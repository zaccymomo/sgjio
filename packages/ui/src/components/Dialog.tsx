import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";

import { cn } from "../lib/cn";

/**
 * A modal dialog built on the browser's own <dialog> element, which supplies the focus
 * trap, Escape to close, the backdrop, and returning focus to the button that opened it.
 *
 * The parent owns `open`. `onClose` is called when the reader asks to close (the close
 * button, Escape, or a click on the backdrop); the parent then sets `open` to false.
 * While a request is running, pass `dismissible={false}` so it can't be closed halfway.
 *
 * Children are only mounted while open, so a form inside starts empty each time.
 *
 * The browser focuses the first focusable thing when a dialog opens, which here would be
 * the close button. Mark the element that should get focus instead (the name field, or
 * Cancel on a destructive confirmation) with `data-autofocus`.
 *
 * Layout follows the app: a sheet along the bottom edge on a phone, a centred card from
 * 640px up.
 */
export function Dialog({
  open,
  title,
  onClose,
  dismissible = true,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  dismissible?: boolean;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  // Where a press began, so selecting text in a field and letting go over the backdrop
  // doesn't close the dialog.
  const pressedBackdrop = useRef(false);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
      dialog.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    }
    if (!open && dialog.open) dialog.close();
  }, [open]);

  function requestClose() {
    if (dismissible) onClose();
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      // Escape: keep the dialog open until the parent says otherwise.
      onCancel={(event) => {
        event.preventDefault();
        requestClose();
      }}
      // The content fills the dialog's box, so a press that lands on the dialog element
      // itself is a press on the backdrop.
      onPointerDown={(event) => {
        pressedBackdrop.current = event.target === event.currentTarget;
      }}
      onClick={(event) => {
        if (pressedBackdrop.current && event.target === event.currentTarget) requestClose();
        pressedBackdrop.current = false;
      }}
      className={cn(
        "m-0 mt-auto w-full max-w-full rounded-t-lg bg-white p-0 text-ink shadow-xl",
        "backdrop:bg-ink/50 sm:m-auto sm:max-w-md sm:rounded-lg",
      )}
    >
      {open && (
        <div className="max-h-[85dvh] overflow-y-auto overscroll-contain p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))]">
          <div className="flex items-start justify-between gap-3">
            <h2 id={titleId} className="text-base font-bold text-ink">
              {title}
            </h2>
            <button
              type="button"
              onClick={requestClose}
              disabled={!dismissible}
              aria-label="Close"
              className="-mt-1 -mr-1.5 flex size-9 shrink-0 items-center justify-center rounded-sm text-muted hover:bg-surface hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-60"
            >
              <X className="size-4" aria-hidden />
            </button>
          </div>
          <div className="mt-3">{children}</div>
        </div>
      )}
    </dialog>
  );
}
