import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";

import { cn } from "../lib/cn";

/**
 * A modal dialog on the browser's own <dialog> element, which supplies the focus trap,
 * Escape, the backdrop, and putting focus back on whatever opened it.
 *
 * The parent owns `open`. `onClose` is called when the reader asks to close: the close
 * button, Escape, or a click on the backdrop. Pass `dismissible={false}` while a request
 * runs, so the dialog cannot be closed halfway through.
 *
 * Children mount only while open, so a form inside starts fresh each time. Focus goes to
 * the element marked `data-autofocus` (the name field, or Cancel on a destructive
 * confirmation), otherwise to the first focusable element.
 *
 * At phone width it is a sheet along the bottom edge; from 640px up, a centred card.
 */
export function Dialog({
  open,
  title,
  description,
  onClose,
  dismissible = true,
  children,
  footer,
}: {
  open: boolean;
  title: string;
  description?: ReactNode;
  onClose: () => void;
  dismissible?: boolean;
  children?: ReactNode;
  /** Action buttons. Stacked full width on a phone, in a row on the right otherwise. */
  footer?: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  // Where the press began, so selecting text in a field and letting go over the backdrop
  // does not close the dialog.
  const pressStartedOnBackdrop = useRef(false);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog || !open) return;
    dialog.showModal();
    dialog.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    // The page behind should not scroll while the dialog is open.
    const root = document.documentElement;
    const previousOverflow = root.style.overflow;
    root.style.overflow = "hidden";
    return () => {
      root.style.overflow = previousOverflow;
      dialog.close();
    };
  }, [open]);

  function requestClose() {
    if (dismissible) onClose();
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      onCancel={(event) => {
        // Escape: stay open until the parent says otherwise.
        event.preventDefault();
        requestClose();
      }}
      // The content fills the dialog's box, so a press on the dialog element itself is a
      // press on the backdrop.
      onPointerDown={(event) => {
        pressStartedOnBackdrop.current = event.target === event.currentTarget;
      }}
      onClick={(event) => {
        if (pressStartedOnBackdrop.current && event.target === event.currentTarget) {
          requestClose();
        }
        pressStartedOnBackdrop.current = false;
      }}
      className={cn(
        "m-0 mt-auto w-full max-w-none rounded-t-lg bg-white p-0 text-ink shadow-xl",
        "backdrop:bg-ink/50 sm:m-auto sm:w-[calc(100%-2rem)] sm:max-w-md sm:rounded-lg",
      )}
    >
      {open && (
        <div className="flex max-h-[85dvh] flex-col gap-4 overflow-y-auto overscroll-contain p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))]">
          <div className="flex items-start justify-between gap-3">
            <div className="flex min-w-0 flex-col gap-1">
              <h2 id={titleId} className="text-base font-bold break-words text-ink">
                {title}
              </h2>
              {description && (
                <div id={descriptionId} className="text-sm text-muted">
                  {description}
                </div>
              )}
            </div>
            <button
              type="button"
              onClick={requestClose}
              disabled={!dismissible}
              aria-label="Close"
              className="-mt-1.5 -mr-2 flex size-9 shrink-0 items-center justify-center rounded-sm text-muted hover:bg-surface hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-60"
            >
              <X className="size-4" aria-hidden />
            </button>
          </div>
          {children}
          {footer && (
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">{footer}</div>
          )}
        </div>
      )}
    </dialog>
  );
}
