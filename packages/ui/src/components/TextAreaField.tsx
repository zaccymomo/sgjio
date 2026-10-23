import { useId, type ComponentProps } from "react";

import { cn } from "../lib/cn";

export type TextAreaFieldProps = ComponentProps<"textarea"> & {
  label: string;
  /** When set, the field is highlighted and the message shown below it. */
  error?: string;
  /** Helper text shown below the field when there is no error. */
  hint?: string;
};

/**
 * A labelled multi-line text box, for a sentence or two such as a topic's description.
 * Looks and behaves like TextField: same label, border, error highlight and message.
 */
export function TextAreaField({
  label,
  error,
  hint,
  id,
  className,
  rows = 3,
  ...props
}: TextAreaFieldProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const messageId = `${inputId}-message`;
  const message = error ?? hint;

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={inputId} className="text-xs font-semibold text-ink">
        {label}
      </label>
      <textarea
        id={inputId}
        rows={rows}
        aria-invalid={error ? true : undefined}
        aria-describedby={message ? messageId : undefined}
        className={cn(
          "w-full resize-y rounded-sm border bg-white px-3 py-2.5 text-sm text-ink placeholder:text-subtle",
          "outline-none transition-colors focus:ring-2",
          error
            ? "border-danger focus:ring-danger/20"
            : "border-line focus:border-ink focus:ring-ink/10",
        )}
        {...props}
      />
      {message && (
        <p id={messageId} className={cn("text-xs", error ? "text-danger" : "text-muted")}>
          {message}
        </p>
      )}
    </div>
  );
}
