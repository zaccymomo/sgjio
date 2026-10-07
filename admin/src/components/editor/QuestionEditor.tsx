import { cn } from "@sgjio/ui";
import type { ChoiceQuestion, Issue } from "@sgjio/ui/lesson";
import { Check, Plus, Shuffle, Trash2, X } from "lucide-react";
import { useId } from "react";

import { markCorrect, newOption } from "../../lib/cards";
import { MAX_OPTION_TEXT, MAX_OPTIONS } from "../../lib/lessons";
import { MarkdownField } from "../MarkdownField";

/**
 * A card's question (SCRUM-19): one to four options, exactly one marked correct (choosing
 * another moves the mark, AC2), an optional "why not" for each wrong one, and the
 * explanation learners see after answering (AC3).
 */
export function QuestionEditor({
  question,
  hasBlank,
  issues,
  onChange,
  onRemove,
}: {
  question: ChoiceQuestion;
  hasBlank: boolean;
  /** This card's issues, to show by the field they are about. */
  issues: Issue[];
  onChange: (change: Partial<ChoiceQuestion>) => void;
  onRemove: () => void;
}) {
  const groupName = useId();
  const single = question.options.length === 1;
  const issueFor = (field: string) => issues.find((issue) => issue.field === field);
  const listIssue = issueFor("question.options");
  const explanationIssue = issueFor("question.explanation");

  function setOption(id: string, change: { text?: string; why_not?: string }) {
    onChange({
      options: question.options.map((option) =>
        option.id === id ? { ...option, ...change } : option,
      ),
    });
  }

  return (
    <section
      aria-label="Question"
      className="flex flex-col gap-4 rounded-lg border border-line bg-white p-4"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold text-ink">Question</h3>
          <p className="text-xs text-muted">
            {hasBlank
              ? "Learners fill the blank by choosing an option. Keep options short."
              : "The options show as answer cards below the text. Insert a blank to make it fill-in-the-blank."}
          </p>
        </div>
        <button
          type="button"
          onClick={onRemove}
          className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-sm px-2 text-xs font-semibold text-muted hover:bg-surface hover:text-danger"
        >
          <Trash2 className="size-3.5" aria-hidden />
          Remove question
        </button>
      </div>

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1.5 flex w-full items-center justify-between text-xs font-semibold text-ink">
          <span>
            Options{" "}
            {!single && <span className="font-normal text-muted">· select the correct one</span>}
          </span>
        </legend>
        {question.options.map((option, n) => {
          const textIssue = issueFor(`question.options.${option.id}`);
          return (
            <div
              key={option.id}
              className={cn(
                "flex flex-col gap-2 rounded-md border p-2 transition-colors",
                option.correct && !single ? "border-success/40 bg-success-soft/60" : "border-line",
              )}
            >
              <div className="flex items-center gap-2">
                {single ? (
                  <span
                    className="flex size-8 shrink-0 items-center justify-center text-success"
                    title="The only option is the answer"
                  >
                    <Check className="size-4" strokeWidth={3} aria-hidden />
                  </span>
                ) : (
                  <label
                    className={cn(
                      "flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-full border-2 transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-brand",
                      option.correct
                        ? "border-success bg-success text-white"
                        : "border-line text-transparent hover:border-success/60",
                    )}
                    title="Mark as the correct answer"
                  >
                    <input
                      type="radio"
                      name={groupName}
                      checked={option.correct}
                      onChange={() => onChange({ options: markCorrect(question, option.id) })}
                      className="sr-only"
                      aria-label={`Option ${n + 1} is correct`}
                    />
                    <Check className="size-4" strokeWidth={3} aria-hidden />
                  </label>
                )}
                <input
                  value={option.text}
                  onChange={(event) => setOption(option.id, { text: event.target.value })}
                  maxLength={MAX_OPTION_TEXT}
                  placeholder={`Option ${n + 1}`}
                  aria-label={`Option ${n + 1}`}
                  aria-invalid={textIssue ? true : undefined}
                  className={cn(
                    "h-9 min-w-0 flex-1 rounded-sm border bg-white px-2.5 text-sm text-ink outline-none placeholder:text-subtle focus:ring-2",
                    textIssue
                      ? "border-danger focus:ring-danger/20"
                      : "border-line focus:border-ink focus:ring-ink/10",
                  )}
                />
                {question.options.length > 1 && (
                  <button
                    type="button"
                    onClick={() =>
                      onChange({ options: question.options.filter((o) => o.id !== option.id) })
                    }
                    aria-label={`Remove option ${n + 1}`}
                    className="flex size-8 shrink-0 items-center justify-center rounded-sm text-subtle hover:bg-surface hover:text-danger"
                  >
                    <X className="size-4" aria-hidden />
                  </button>
                )}
              </div>
              {!option.correct && !single && (
                <input
                  value={option.why_not}
                  onChange={(event) => setOption(option.id, { why_not: event.target.value })}
                  maxLength={400}
                  placeholder="Why not? Shown if a learner picks this (optional)"
                  aria-label={`Why option ${n + 1} is wrong`}
                  className="ml-10 h-8 rounded-sm border border-transparent bg-surface px-2.5 text-xs text-ink outline-none placeholder:text-subtle focus:border-line focus:bg-white"
                />
              )}
            </div>
          );
        })}
        {listIssue && <p className="text-xs text-danger">{listIssue.message}</p>}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <button
            type="button"
            onClick={() => onChange({ options: [...question.options, newOption()] })}
            disabled={question.options.length >= MAX_OPTIONS}
            className="inline-flex h-8 items-center gap-1.5 rounded-sm px-2 text-xs font-semibold text-ink hover:bg-surface disabled:cursor-not-allowed disabled:text-subtle"
          >
            <Plus className="size-3.5" aria-hidden />
            Add option
            <span className="font-normal text-muted">
              ({question.options.length} of {MAX_OPTIONS})
            </span>
          </button>
          {question.options.length >= 2 ? (
            <label className="inline-flex cursor-pointer items-center gap-2 text-xs text-ink">
              <input
                type="checkbox"
                checked={question.shuffle}
                onChange={(event) => onChange({ shuffle: event.target.checked })}
                className="size-4 accent-ink"
              />
              <Shuffle className="size-3.5 text-muted" aria-hidden />
              Shuffle for learners
            </label>
          ) : (
            <p className="text-xs text-muted">One option: a tap to fill the blank, not scored.</p>
          )}
        </div>
      </fieldset>

      <MarkdownField
        label="Explanation"
        value={question.explanation}
        onChange={(explanation) => onChange({ explanation })}
        rows={3}
        maxLength={800}
        error={explanationIssue?.message}
        hint="Shown after answering, right or wrong: why this is the norm."
      />
    </section>
  );
}
