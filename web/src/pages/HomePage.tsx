import {
  Button,
  Dialog,
  ErrorState,
  Placeholder,
  ProgressRing,
  Spinner,
  cn,
  useAuth,
} from "@sgjio/ui";
import { Info } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { type Progress, type TopicProgress, useProgress } from "../lib/progress";

/**
 * The landing page is the portfolio (SCRUM-43): one progress circle per topic that has a
 * published lesson, plus one overall figure. Selecting a circle opens that topic
 * (SCRUM-53). The suggested lesson beside it is SCRUM-6.
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

      {state.status === "loading" && (
        <div className="flex justify-center py-16 text-brand">
          <Spinner className="size-6" label="Loading your progress" />
        </div>
      )}

      {/* AC10: say so and offer a retry, rather than drawing empty circles that would
          read as "no progress". */}
      {state.status === "error" && <ErrorState message={state.message} onRetry={reload} />}

      {state.status === "ready" && <ProgressSection progress={state.progress} />}

      <Placeholder story="SCRUM-6" title="Suggested for you">
        The next lesson, drawn from the topic where progress is weakest.
      </Placeholder>
    </div>
  );
}

function ProgressSection({ progress }: { progress: Progress }) {
  const { topics, completed, available } = progress;
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
          <span className="text-muted">lessons completed</span>
        </p>
      </div>

      <div className="mt-2.5 h-1.5 w-full overflow-hidden rounded-full bg-line">
        <div
          className="h-full rounded-full bg-brand transition-[width] duration-500"
          style={{ width: `${(completed / available) * 100}%` }}
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
        topic && `${topic.name}: ${topic.completed} of ${topic.available} lessons completed.`
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
          Each circle counts the lessons you&apos;ve completed out of the lessons available in that
          topic.
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
  const { id, name, completed, available } = topic;
  const isComplete = completed >= available;
  const status = isComplete ? "Complete" : completed === 0 ? "Not started" : "In progress";

  return (
    <Link
      to={`/topics/${id}`}
      // One label for the whole tile: the ring, the name and the status read as a
      // sentence instead of three fragments.
      aria-label={`${name}: ${completed} of ${available} lessons completed. ${status}.`}
      className={cn(
        // pt-6 leaves room for the explanation button in the top-right corner.
        "flex h-full flex-col items-center gap-1.5 rounded-lg border border-line bg-white px-2 pt-6 pb-3",
        "transition-colors hover:border-brand/40 hover:bg-brand-soft/40",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
      )}
    >
      <ProgressRing completed={completed} available={available} />
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
