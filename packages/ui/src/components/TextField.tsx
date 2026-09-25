import { useId, type ComponentProps, type ReactNode } from "react";

import { cn } from "../lib/cn";

export type TextFieldProps = ComponentProps<"input"> & {
  label: string;
  /** When set, the field is highlighted and the message shown below it. */
  error?: string;
  /** Helper text shown below the field when there is no error. */
  hint?: string;
  /** Content inside the right edge of the input, e.g. a show/hide button. */
  endAdornment?: ReactNode;
};

/**
 * A labelled input with an error-highlight state.
 *
 * The highlight is what SCRUM-61 AC6, SCRUM-62 AC3 and SCRUM-68 AC3 mean by "the empty
 * field is highlighted": a red border, aria-invalid, and the message read out by screen
 * readers.
 */
export function TextField({
  label,
  error,
  hint,
  endAdornment,
  id,
  className,
  ...props
}: TextFieldProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const messageId = `${inputId}-message`;
  const message = error ?? hint;

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={inputId} className="text-xs font-semibold text-ink">
        {label}
      </label>
      <div className="relative">
        <input
          id={inputId}
          aria-invalid={error ? true : undefined}
          aria-describedby={message ? messageId : undefined}
          className={cn(
            "h-11 w-full rounded-sm border bg-white px-3 text-sm text-ink placeholder:text-subtle",
            "outline-none transition-colors focus:ring-2",
            error
              ? "border-danger focus:ring-danger/20"
              : "border-line focus:border-ink focus:ring-ink/10",
            endAdornment ? "pr-11" : undefined,
          )}
          {...props}
        />
        {endAdornment && (
          <div className="absolute inset-y-0 right-0 flex items-center pr-1">{endAdornment}</div>
        )}
      </div>
      {message && (
        <p id={messageId} className={cn("text-xs", error ? "text-danger" : "text-muted")}>
          {message}
        </p>
      )}
    </div>
  );
}
