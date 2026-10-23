import { ErrorState, Spinner, cn } from "@sgjio/ui";
import { LessonText } from "@sgjio/ui/lesson";
import { Check, ChevronDown, ChevronLeft, ChevronRight, PartyPopper, X } from "lucide-react";
import { useId, useState } from "react";
import { Link } from "react-router-dom";

import { type Mistake, useReview } from "../lib/review";

/**
 * Reviewing mistakes (SCRUM-44), opened from the landing page: only the questions whose
 * latest answer was wrong (AC1). Opening one shows the right answer and why it is the norm
 * (AC2), with a way to the lesson it came from (AC3). With none, the page says there is
 * nothing to review (AC4). Getting a question right on a retake takes it off the list.
 */
export function ReviewPage() {
  const { state, reload } = useReview();

  return (
    <div className="flex flex-col gap-4">
      <Link
        to="/"
        className="inline-flex w-fit items-center gap-1 rounded-sm text-sm font-medium text-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
      >
        <ChevronLeft className="size-4" aria-hidden />
        Your progress
      </Link>

      <div>
        <h1 className="text-[22px] font-bold text-ink">Review mistakes</h1>
        <p className="mt-1 text-sm text-muted">
          The questions you last answered incorrectly. Get one right in its lesson and it leaves
          this list.
        </p>
      </div>

      {state.status === "loading" && (
        <div className="flex justify-center py-16 text-brand">
          <Spinner className="size-6" label="Loading your mistakes" />
        </div>
      )}

      {state.status === "error" && <ErrorState message={state.message} onRetry={reload} />}

      {state.status === "ready" &&
        (state.mistakes.length === 0 ? (
          <section className="flex flex-col items-center gap-2 rounded-lg border border-line bg-surface p-5 text-center">
            <PartyPopper className="size-6 text-brand" aria-hidden />
            <p className="text-sm font-semibold text-ink">Nothing to review</p>
            <p className="text-sm text-muted">
              You haven&apos;t answered any questions incorrectly. Questions you miss in a lesson
              will appear here.
            </p>
          </section>
        ) : (
          <ul className="flex flex-col gap-2.5">
            {state.mistakes.map((mistake) => (
              <li key={`${mistake.lesson_id}:${mistake.question_id}`}>
                <MistakeItem mistake={mistake} />
              </li>
            ))}
          </ul>
        ))}
    </div>
  );
}

function MistakeItem({ mistake }: { mistake: Mistake }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();

  return (
    <article className="overflow-hidden rounded-lg border border-line bg-white">
      <div className="flex items-start gap-3 px-3.5 pt-3">
        <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-danger/10 text-danger">
          <X className="size-4" strokeWidth={3} aria-hidden />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <LessonText text={mistake.text} className="text-sm text-ink" />
          <p className="text-caption text-subtle">
            {mistake.topic_name} · {mistake.lesson_title}
          </p>
        </div>
      </div>
      {/* Its own button rather than the whole card, since the card's text is block content
          that a button cannot hold. */}
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen(!open)}
        className={cn(
          "mt-1 flex w-full items-center gap-1 px-3.5 pt-1 pb-3 pl-[3.25rem] text-left text-sm font-semibold text-brand hover:underline",
          "focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand",
        )}
      >
        {open ? "Hide the answer" : "Show the answer"}
        <ChevronDown
          className={cn("size-4 transition-transform", open && "rotate-180")}
          aria-hidden
        />
      </button>

      {open && (
        <div id={panelId} className="flex flex-col gap-3 border-t border-line px-3.5 py-3">
          <dl className="flex flex-col gap-2 text-sm">
            <div className="flex items-start gap-2">
              <X className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />
              <div>
                <dt className="text-caption text-muted">Your answer</dt>
                <dd className="font-semibold text-ink">
                  {mistake.chosen || "An option since removed"}
                </dd>
                {mistake.why_not && <dd className="mt-0.5 text-muted">{mistake.why_not}</dd>}
              </div>
            </div>
            <div className="flex items-start gap-2">
              <Check className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
              <div>
                <dt className="text-caption text-muted">Correct answer</dt>
                <dd className="font-semibold text-ink">{mistake.correct}</dd>
              </div>
            </div>
          </dl>
          {mistake.explanation && (
            <div className="rounded-md bg-surface p-3">
              <p className="text-caption font-semibold text-muted">Why this is the norm</p>
              <LessonText text={mistake.explanation} className="mt-1 text-sm text-ink" />
            </div>
          )}
          <Link
            to={`/lessons/${mistake.lesson_id}`}
            className="inline-flex w-fit items-center gap-1 rounded-sm text-sm font-semibold text-brand hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          >
            Go to the lesson: {mistake.lesson_title}
            <ChevronRight className="size-4" aria-hidden />
          </Link>
        </div>
      )}
    </article>
  );
}
