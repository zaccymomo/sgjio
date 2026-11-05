import { Button, Dialog, ErrorState, ProgressRing, Spinner, cn, useAuth } from "@sgjio/ui";
import { readingLabel } from "@sgjio/ui/lesson";
import { ChevronRight, Info, PartyPopper, RotateCcw, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { LessonSearch } from "../components/LessonSearch";
import { type Progress, type Suggestion, type TopicProgress, useProgress } from "../lib/progress";

/**
 * The landing page is the portfolio (SCRUM-43): one progress circle per topic that has a
 * published lesson, plus one overall figure. Selecting a circle opens that topic
 * (SCRUM-53). Below the circles is one suggested lesson, from the topic where progress is
 * weakest (SCRUM-6); the circles stay the way to pick any topic instead. Then a way to review
 * the questions answered wrongly (SCRUM-44).
 *
 * Above them all, a search bar finds a lesson in any topic by a word or phrase (SCRUM-85).
 */
export function HomePage() {
  const { user } = useAuth();
  const { state, reload } = useProgress();

  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="text-sm font-medium text-muted">Welcome back,</p>
        <h1 className="text-[22px] font-bold text-ink">{user?.name}</h1>
      </div>

      <LessonSearch />

      {state.status === "loading" && (
        <div className="flex justify-center py-16 text-brand">
          <Spinner className="size-6" label="Loading your progress" />
        </div>
      )}

      {/* AC10: say so and offer a retry, rather than drawing empty circles that would
          read as "no progress". */}
      {state.status === "error" && <ErrorState message={state.message} onRetry={reload} />}

      {state.status === "ready" && (
        <>
          {user?.user_type === "newcomer" && !state.progress.aptitude_taken && (
            <section className="flex items-center justify-between gap-3 rounded-lg border border-brand/30 bg-brand-soft/40 p-3.5">
              <div>
                <p className="text-sm font-semibold text-ink">Find your starting point</p>
                <p className="text-caption text-muted">
                  Take the quiz to exempt lessons in topics you already understand.
                </p>
              </div>
              <Link
                to="/aptitude"
                className="shrink-0 rounded-sm bg-ink px-3 py-2 text-xs font-semibold text-white"
              >
                Take quiz
              </Link>
            </section>
          )}
          <ProgressSection progress={state.progress} />
          {state.progress.available > 0 && (
            <>
              <SuggestionSection suggestion={state.progress.suggestion} />
              {/* SCRUM-44 AC1 */}
              <Link
                to="/review"
                className={cn(
                  "flex items-center gap-3 rounded-lg border border-line bg-white px-3.5 py-3",
                  "transition-colors hover:border-brand/40 hover:bg-brand-soft/40",
                  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
                )}
              >
                <RotateCcw className="size-5 shrink-0 text-brand" aria-hidden />
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="text-sm font-semibold text-ink">Review mistakes</span>
                  <span className="text-caption text-subtle">
                    See the right answers to questions you missed
                  </span>
                </span>
                <ChevronRight className="size-4 shrink-0 text-subtle" aria-hidden />
              </Link>
            </>
          )}
        </>
      )}
    </div>
  );
}

function ProgressSection({ progress }: { progress: Progress }) {
  const { topics, completed, exempted, available } = progress;
  // The circle whose explanation is open (SCRUM-46), or null when it is closed.
  const [explaining, setExplaining] = useState<TopicProgress | null>(null);

  if (available === 0) {
    return (
      <section className="rounded-lg border border-line bg-surface p-5 text-center">
        <p className="text-sm font-semibold text-ink">No lessons yet</p>
        <p className="mt-1 text-sm text-muted">
          Your progress circles appear here as soon as the first lesson is published.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-line bg-surface p-3.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 className="text-caption font-semibold tracking-wide text-muted uppercase">
          Your progress
        </h2>
        <p className="text-sm">
          <span className="font-bold text-ink">
            {completed} / {available}
          </span>{" "}
          <span className="text-muted">lessons covered</span>
        </p>
      </div>

      {exempted > 0 && (
        <p className="mt-1 text-right text-caption text-muted">
          Includes {exempted} {exempted === 1 ? "lesson" : "lessons"} exempted by your aptitude quiz
          · {/* SCRUM-100: back to the quiz results that explain it. */}
          <Link
            to="/aptitude/results"
            className="font-semibold text-brand hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          >
            See why
          </Link>
        </p>
      )}

      {/* Lessons the user completed in full red, then those the quiz exempted in a lighter
          red (SCRUM-100), as in the circles. */}
      <div className="mt-2.5 flex h-1.5 w-full overflow-hidden rounded-full bg-line">
        <div
          className="h-full bg-brand transition-[width] duration-500"
          style={{ width: `${((completed - exempted) / available) * 100}%` }}
        />
        <div
          className="h-full bg-brand-light transition-[width] duration-500"
          style={{ width: `${(exempted / available) * 100}%` }}
        />
      </div>

      {/* AC7: with nothing completed, point at the suggestion rather than leaving a
          screen of empty circles with no next step. */}
      <p className="mt-3 text-caption text-muted">
        {completed === 0
          ? "You haven't completed a lesson yet. Start with the suggestion below, or select a topic."
          : "Select a topic to see its lessons and quizzes"}
      </p>

      <ul className="mt-3 grid grid-cols-3 gap-2.5 md:grid-cols-4">
        {topics.map((topic) => (
          // The explanation button sits beside the link rather than inside it, since a
          // button inside a link is invalid and would also open the topic.
          <li key={topic.id} className="relative">
            <TopicCircle topic={topic} />
            <button
              type="button"
              onClick={() => setExplaining(topic)}
              aria-label={`How the ${topic.name} circle is filled`}
              className={cn(
                "absolute top-1 right-1 flex size-8 items-center justify-center rounded-sm",
                "text-subtle hover:bg-surface hover:text-ink",
                "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
              )}
            >
              <Info className="size-4" aria-hidden />
            </button>
          </li>
        ))}
      </ul>

      <CircleExplanation topic={explaining} onClose={() => setExplaining(null)} />
    </section>
  );
}

/**
 * SCRUM-6: the suggested next lesson. The figures reload on return from a lesson, so
 * completing it brings the next suggestion straight away (AC4). With every lesson completed
 * there is none, and the page says so (AC6).
 */
function SuggestionSection({ suggestion }: { suggestion: Suggestion | null }) {
  return (
    <section className="flex flex-col gap-2.5">
      <h2 className="text-caption font-semibold tracking-wide text-muted uppercase">
        Suggested for you
      </h2>
      {suggestion ? (
        <Link
          to={`/lessons/${suggestion.lesson_id}`}
          aria-label={`Suggested lesson: ${suggestion.title}, in ${suggestion.topic_name}. ${readingLabel(suggestion.reading_seconds)}.`}
          className={cn(
            "flex items-center gap-3 rounded-lg border border-brand/30 bg-brand-soft/40 px-3.5 py-3",
            "transition-colors hover:border-brand/60 hover:bg-brand-soft/70",
            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
          )}
        >
          <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-brand text-white">
            <Sparkles className="size-5" aria-hidden />
          </span>
          <span className="flex min-w-0 flex-1 flex-col" aria-hidden>
            <span className="text-sm font-semibold text-ink">{suggestion.title}</span>
            {suggestion.summary && (
              <span className="text-caption text-muted">{suggestion.summary}</span>
            )}
            <span className="text-caption text-subtle">
              {suggestion.topic_name} · {readingLabel(suggestion.reading_seconds)}
            </span>
          </span>
          <ChevronRight className="size-4 shrink-0 text-subtle" aria-hidden />
        </Link>
      ) : (
        <div className="flex items-center gap-3 rounded-lg border border-line bg-surface px-3.5 py-3">
          <PartyPopper className="size-5 shrink-0 text-brand" aria-hidden />
          <p className="text-sm text-ink">
            You&apos;ve completed every lesson available. There&apos;s nothing further for now; new
            lessons will appear here when they&apos;re published.
          </p>
        </div>
      )}
    </section>
  );
}

/**
 * SCRUM-46: what fills a circle and how quiz results are used, in plain language.
 * Closing it only clears the open topic, so the landing page is left as it was (AC5).
 */
function CircleExplanation({
  topic,
  onClose,
}: {
  topic: TopicProgress | null;
  onClose: () => void;
}) {
  return (
    <Dialog
      open={topic !== null}
      title="How your circles are filled"
      description={
        topic &&
        `${topic.name}: ${topic.completed} of ${topic.available} lessons covered, including ${topic.exempted} exempted.`
      }
      onClose={onClose}
      footer={
        <Button data-autofocus onClick={onClose}>
          Got it
        </Button>
      }
    >
      <ul className="flex list-disc flex-col gap-2 pl-5 text-sm text-ink">
        {/* AC1 */}
        <li>
          Each circle counts lessons you completed and lessons exempted by your topic placement.
        </li>
        {/* AC2 */}
        <li>Finishing a lesson completes it, even if you answered some questions incorrectly.</li>
        {/* AC3: finish() in api/app/learning.py keeps the best score. */}
        <li>
          Your quiz results are recorded separately and count toward your tier. We keep your best
          result, so retaking a quiz until you get it right counts in full.
        </li>
        {/* AC4 */}
        <li>
          A circle reflects the lessons in the topic right now. When new lessons are added, the
          circle fills a smaller share until you complete them too.
        </li>
      </ul>
    </Dialog>
  );
}

function TopicCircle({ topic }: { topic: TopicProgress }) {
  const { id, name, completed, exempted, available } = topic;
  const isComplete = completed >= available;
  const status = isComplete ? "Complete" : completed === 0 ? "Not started" : "In progress";
  const includes = exempted > 0 ? `, including ${exempted} exempted` : "";

  return (
    <Link
      to={`/topics/${id}`}
      // One label for the whole tile: the ring, the name and the status read as a
      // sentence instead of three fragments.
      aria-label={`${name}: ${completed} of ${available} lessons completed${includes}. ${status}.`}
      className={cn(
        // pt-6 leaves room for the explanation button in the top-right corner.
        "flex h-full flex-col items-center gap-1.5 rounded-lg border border-line bg-white px-2 pt-6 pb-3",
        "transition-colors hover:border-brand/40 hover:bg-brand-soft/40",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
      )}
    >
      <ProgressRing completed={completed} exempted={exempted} available={available} />
      <span className="text-center text-xs font-semibold text-ink" aria-hidden>
        {name}
      </span>
      {/* mt-auto pins the status to the bottom, so it stays level across a row even
          when a longer topic name wraps onto two lines. */}
      <span
        className={cn("mt-auto text-2xs", isComplete ? "font-semibold text-brand" : "text-subtle")}
        aria-hidden
      >
        {status}
      </span>
    </Link>
  );
}
