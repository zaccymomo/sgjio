import { cn } from "@sgjio/ui";
import { BLANK_TOKEN, hasBlank } from "@sgjio/ui/lesson";
import {
  Bold,
  Italic,
  List,
  ListOrdered,
  RectangleHorizontal,
  type LucideIcon,
} from "lucide-react";
import { useId, useRef, type KeyboardEvent } from "react";

import { plural } from "../lib/format";
import { applyEdit, formatEdit, insertEdit, type Edit, type Format } from "../lib/markdownEdits";
import { countWords } from "../lib/words";

const BUTTONS: { format: Format; label: string; icon: LucideIcon; shortcut?: string }[] = [
  { format: "bold", label: "Bold", icon: Bold, shortcut: "Ctrl+B" },
  {
    format: "italic",
    label: "Italic, for Singlish and Malay words",
    icon: Italic,
    shortcut: "Ctrl+I",
  },
  { format: "bullets", label: "Bulleted list", icon: List },
  { format: "numbers", label: "Numbered list", icon: ListOrdered },
];

/**
 * Text written in Markdown, with buttons for bold, italics and lists (SCRUM-64 AC3) and, for
 * a card's text, for the blank its question fills (SCRUM-19).
 *
 * The buttons insert the Markdown, so what is saved is exactly what is shown. They go
 * through the browser's own editing where it can, so Undo still works after using them.
 */
export function MarkdownField({
  label,
  value,
  onChange,
  error,
  hint,
  rows = 5,
  blank,
  wordLimit,
  maxLength,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  hint?: string;
  rows?: number;
  /** Offer "Insert blank" (a card's text): at most one per card. */
  blank?: boolean;
  /** Show the word count, warning above this many. */
  wordLimit?: number;
  maxLength?: number;
  placeholder?: string;
}) {
  const id = useId();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messageId = `${id}-message`;
  const words = countWords(value.replace(/\{\{\s*blank\s*\}\}/g, " "));
  const hasOne = hasBlank(value);

  function apply(edit: Edit) {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.focus();
    textarea.setSelectionRange(edit.from, edit.to);
    // execCommand is deprecated but is still the only way to change a field's text and keep
    // it on the browser's undo stack. It fires the input event, so React sees the change.
    const done = document.execCommand("insertText", false, edit.insert);
    if (!done) onChange(applyEdit(textarea.value, edit));
    // After React has applied the new value.
    requestAnimationFrame(() => textarea.setSelectionRange(edit.selectionStart, edit.selectionEnd));
  }

  function format(kind: Format) {
    const textarea = textareaRef.current;
    if (textarea)
      apply(formatEdit(kind, textarea.value, textarea.selectionStart, textarea.selectionEnd));
  }

  function insertBlank() {
    const textarea = textareaRef.current;
    if (textarea && !hasOne)
      apply(
        insertEdit(BLANK_TOKEN, textarea.value, textarea.selectionStart, textarea.selectionEnd),
      );
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
    const key = event.key.toLowerCase();
    if (key === "b" || key === "i") {
      event.preventDefault();
      format(key === "b" ? "bold" : "italic");
    }
  }

  const toolbarButton =
    "flex h-8 items-center justify-center gap-1.5 rounded-sm px-2 text-muted hover:bg-white hover:text-ink focus-visible:outline-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-50";

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-xs font-semibold text-ink">
        {label}
      </label>
      <div
        className={cn(
          "overflow-hidden rounded-md border bg-white transition-colors focus-within:ring-2",
          error
            ? "border-danger focus-within:ring-danger/20"
            : "border-line focus-within:border-ink focus-within:ring-ink/10",
        )}
      >
        <div
          role="toolbar"
          aria-label="Formatting"
          aria-controls={id}
          className="flex flex-wrap items-center gap-0.5 border-b border-line bg-surface p-1"
        >
          {BUTTONS.map(({ format: kind, label: name, icon: Icon, shortcut }) => (
            <button
              key={kind}
              type="button"
              onClick={() => format(kind)}
              // Keep the selection in the text while the button is pressed.
              onMouseDown={(event) => event.preventDefault()}
              aria-label={name}
              title={shortcut ? `${name} (${shortcut})` : name}
              className={cn(toolbarButton, "w-8 px-0")}
            >
              <Icon className="size-4" aria-hidden />
            </button>
          ))}
          {blank && (
            <>
              <span className="mx-1 h-5 w-px bg-line" aria-hidden />
              <button
                type="button"
                onClick={insertBlank}
                onMouseDown={(event) => event.preventDefault()}
                disabled={hasOne}
                title={
                  hasOne ? "A card can have one blank" : "Insert a blank for the question to fill"
                }
                className={cn(toolbarButton, "text-xs font-semibold")}
              >
                <RectangleHorizontal className="size-4" aria-hidden />
                Insert blank
              </button>
            </>
          )}
        </div>
        <textarea
          ref={textareaRef}
          id={id}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          rows={rows}
          maxLength={maxLength}
          aria-invalid={error ? true : undefined}
          aria-describedby={messageId}
          placeholder={placeholder}
          className="block w-full resize-y bg-white px-3 py-2.5 text-sm leading-relaxed text-ink outline-none placeholder:text-subtle"
        />
      </div>
      <div id={messageId} className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
        <p className={cn("text-xs", error ? "text-danger" : "text-muted")}>{error ?? hint}</p>
        {wordLimit !== undefined && (
          <p
            className={cn(
              "shrink-0 text-xs tabular-nums",
              words > wordLimit ? "font-semibold text-amber-700" : "text-subtle",
            )}
          >
            {plural(words, "word")}
            {words > wordLimit && ` · cards read best under ${wordLimit}`}
          </p>
        )}
      </div>
    </div>
  );
}
