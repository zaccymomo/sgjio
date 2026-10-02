import { Alert, cn } from "@sgjio/ui";
import { Bold, Heading2, List, ListOrdered, type LucideIcon } from "lucide-react";
import { useId, useRef, type KeyboardEvent } from "react";

import { plural } from "../lib/format";
import { applyEdit, formatEdit, type Format } from "../lib/markdownEdits";
import { READING_LIMIT_MINUTES, readingTime } from "../lib/readingTime";

const BUTTONS: { format: Format; label: string; icon: LucideIcon; shortcut?: string }[] = [
  { format: "heading", label: "Heading", icon: Heading2 },
  { format: "bold", label: "Bold", icon: Bold, shortcut: "Ctrl+B" },
  { format: "bullets", label: "Bulleted list", icon: List },
  { format: "numbers", label: "Numbered list", icon: ListOrdered },
];

/**
 * The lesson's text, written in Markdown, with buttons for headings, bold and lists
 * (SCRUM-64 AC3) and the estimated reading time (AC4).
 *
 * The buttons insert the Markdown, so what is saved is exactly what is shown. They go
 * through the browser's own editing where it can, so Undo still works after using them.
 */
export function MarkdownField({
  label,
  value,
  onChange,
  error,
  readOnly,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  readOnly?: boolean;
}) {
  const id = useId();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const reading = readingTime(value);
  const messageId = `${id}-message`;

  function format(kind: Format) {
    const textarea = textareaRef.current;
    if (!textarea || readOnly) return;
    const edit = formatEdit(kind, textarea.value, textarea.selectionStart, textarea.selectionEnd);
    textarea.focus();
    textarea.setSelectionRange(edit.from, edit.to);
    // execCommand is deprecated but is still the only way to change a field's text and keep
    // it on the browser's undo stack. It fires the input event, so React sees the change.
    const done = document.execCommand("insertText", false, edit.insert);
    if (!done) onChange(applyEdit(textarea.value, edit));
    // After React has applied the new value.
    requestAnimationFrame(() => textarea.setSelectionRange(edit.selectionStart, edit.selectionEnd));
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === "b") {
      event.preventDefault();
      format("bold");
    }
  }

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-xs font-semibold text-ink">
        {label}
      </label>
      <div
        className={cn(
          "overflow-hidden rounded-sm border bg-white transition-colors focus-within:ring-2",
          error
            ? "border-danger focus-within:ring-danger/20"
            : "border-line focus-within:border-ink focus-within:ring-ink/10",
        )}
      >
        <div
          role="toolbar"
          aria-label="Formatting"
          aria-controls={id}
          className="flex flex-wrap gap-0.5 border-b border-line bg-surface p-1"
        >
          {BUTTONS.map(({ format: kind, label: name, icon: Icon, shortcut }) => (
            <button
              key={kind}
              type="button"
              onClick={() => format(kind)}
              // Keep the selection in the text while the button is pressed.
              onMouseDown={(event) => event.preventDefault()}
              disabled={readOnly}
              aria-label={name}
              title={shortcut ? `${name} (${shortcut})` : name}
              className="flex size-9 items-center justify-center rounded-sm text-muted hover:bg-white hover:text-ink focus-visible:outline-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Icon className="size-4" aria-hidden />
            </button>
          ))}
        </div>
        <textarea
          ref={textareaRef}
          id={id}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          readOnly={readOnly}
          rows={16}
          aria-invalid={error ? true : undefined}
          aria-describedby={messageId}
          placeholder={
            "## A heading\n\nWrite the lesson here. Use **bold** for key words.\n\n- A point\n- Another point"
          }
          className="block min-h-64 w-full resize-y bg-white px-3 py-2.5 text-sm leading-relaxed text-ink outline-none placeholder:text-subtle"
        />
      </div>
      <div id={messageId} className="flex flex-col gap-2">
        {error && <p className="text-xs text-danger">{error}</p>}
        <p className="text-xs text-muted">
          {reading.words === 0
            ? "No text yet."
            : `About ${reading.minutes} min read · ${plural(reading.words, "word")}`}
        </p>
        {/* SCRUM-64 AC4: a warning, never a block. */}
        {reading.overLimit && (
          <Alert tone="info">
            Lessons should take under {READING_LIMIT_MINUTES} minutes to read. This one takes about{" "}
            {reading.minutes}. You can still save it.
          </Alert>
        )}
      </div>
    </div>
  );
}
