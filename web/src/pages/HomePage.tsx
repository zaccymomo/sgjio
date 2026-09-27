import { ErrorState, Placeholder, ProgressRing, Spinner, cn, useAuth } from "@sgjio/ui";
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
          <li key={topic.id}>
            <TopicCircle topic={topic} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function TopicCircle({ topic }: { topic: TopicProgress }) {
  const { id, name, completed, available } = topic;
  const isComplete = completed >= available;
  const status = isComplete ? "Complete" : completed === 0 ? "Not started" : "In progress";

  return (
    <Link
      to={`/topics/${id}`}
      // The topic list has no endpoint of its own yet, so the name travels with the
      // link. SCRUM-53 will load it from the server and this can go.
      state={{ topicName: name }}
      // One label for the whole tile: the ring, the name and the status read as a
      // sentence instead of three fragments.
      aria-label={`${name}: ${completed} of ${available} lessons completed. ${status}.`}
      className={cn(
        "flex h-full flex-col items-center gap-1.5 rounded-lg border border-line bg-white px-2 py-3",
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
