import { Alert, ErrorState, ProgressRing, Spinner, cn } from "@sgjio/ui";
import { readingLabel } from "@sgjio/ui/lesson";
import { Check, ChevronLeft, ChevronRight } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { type Topic, type TopicLesson, useTopic } from "../lib/topic";

/**
 * A topic opened from its progress circle (SCRUM-43 AC9): its lessons in the order
 * administrators set, each marked completed or not (SCRUM-53), with when it was last
 * attempted and the best score so far (SCRUM-54 AC1, AC2). The page reloads on return
 * from a lesson, so a retake's date and score show straight away (AC3 to AC5).
 *
 * Its description, if it has one, sits under the title (SCRUM-86).
 *
 * Selecting a lesson opens it (AC2). The lesson says it came from here, so finishing or
 * closing it steps back to this page rather than stacking a second copy on top (AC3); that
 * keeps the browser's back button, like the "All topics" link, leading home (AC4).
 *
 */
export function TopicPage() {
  const { topicId = "" } = useParams();
  // Keyed so that moving between topics starts again from "loading".
  return <TopicView key={topicId} topicId={topicId} />;
}

function TopicView({ topicId }: { topicId: string }) {
  const { state, reload } = useTopic(topicId);

  return (
    <div className="flex flex-col gap-4">
      <Link
        to="/"
        className="inline-flex w-fit items-center gap-1 rounded-sm text-sm font-medium text-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
      >
        <ChevronLeft className="size-4" aria-hidden />
        All topics
      </Link>

      {state.status === "loading" && (
        <div className="flex justify-center py-16 text-brand">
          <Spinner className="size-6" label="Loading this topic" />
        </div>
      )}

      {state.status === "error" && <ErrorState message={state.message} onRetry={reload} />}

      {state.status === "unavailable" && (
        <Alert tone="error" className="mx-auto mt-8 w-full max-w-sm">
          {state.message}
        </Alert>
      )}

      {state.status === "ready" && <TopicDetail topic={state.topic} />}
    </div>
  );
}

function TopicDetail({ topic }: { topic: Topic }) {
  const { name, description, completed, available, lessons } = topic;
  const questions = lessons.reduce((total, lesson) => total + lesson.questions, 0);

  return (
    <>
      <div>
        <h1 className="text-[22px] font-bold text-ink">{name}</h1>
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      </div>

      {available === 0 ? (
        <section className="rounded-lg border border-line bg-surface p-5 text-center">
          <p className="text-sm font-semibold text-ink">No lessons here yet</p>
          <p className="mt-1 text-sm text-muted">
            This topic&rsquo;s lessons appear here as soon as they are published.
          </p>
        </section>
      ) : (
        <>
          <section className="flex items-center gap-3.5 rounded-lg border border-line bg-surface p-3.5">
            <ProgressRing completed={completed} available={available} size={48} />
            <div>
              <p className="text-sm font-bold text-ink">
                {completed} of {available} {plural(available, "lesson")} completed
              </p>
              <p className="text-caption text-muted">
                {questions} quiz {plural(questions, "question")} in this topic
              </p>
            </div>
          </section>

          <section className="flex flex-col gap-2.5">
            <h2 className="text-caption font-semibold tracking-wide text-muted uppercase">
              Lessons &amp; quizzes
            </h2>
            <ul className="flex flex-col gap-2.5">
              {lessons.map((lesson) => (
                <li key={lesson.id}>
                  <LessonRow lesson={lesson} />
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </>
  );
}

function LessonRow({ lesson }: { lesson: TopicLesson }) {
  const { id, title, completed } = lesson;
  const meta = rowMeta(lesson);

  return (
    <Link
      to={`/lessons/${id}`}
      // Tells the lesson it can step back to this page when it closes (AC3, AC4).
      state={{ from: "topic" }}
      aria-label={`${title}. ${meta}.`}
      className={cn(
        "flex items-center gap-3 rounded-lg border border-line bg-white px-3.5 py-3",
        "transition-colors hover:border-brand/40 hover:bg-brand-soft/40",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
      )}
    >
      {completed ? (
        <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-brand text-white">
          <Check className="size-4" strokeWidth={3} aria-hidden />
        </span>
      ) : (
        <span className="size-6 shrink-0 rounded-full border-2 border-line" aria-hidden />
      )}
      <span className="flex min-w-0 flex-1 flex-col" aria-hidden>
        <span className="text-sm font-semibold text-ink">{title}</span>
        <span className="text-caption text-subtle">{meta}</span>
      </span>
      <ChevronRight className="size-4 shrink-0 text-subtle" aria-hidden />
    </Link>
  );
}

const DATE = new Intl.DateTimeFormat("en-SG", { day: "numeric", month: "short", year: "numeric" });

/**
 * "Last attempted on 11 Oct 2026 · Best score 2 / 3", or for a lesson not attempted yet,
 * "Not attempted yet · About 1 min · 1 quiz question" (timed as the lesson's cover times
 * it). The score is out of the questions answered then, so a lesson revised since keeps
 * the total its best was scored on.
 */
function rowMeta(lesson: TopicLesson): string {
  const { last_attempted_at, best_correct, best_scored, reading_seconds, questions } = lesson;
  if (!last_attempted_at) {
    return [
      "Not attempted yet",
      readingLabel(reading_seconds),
      `${questions} quiz ${plural(questions, "question")}`,
    ].join(" · ");
  }
  const attempted = `Last attempted on ${DATE.format(new Date(last_attempted_at))}`;
  // A lesson of one-option taps only has nothing to score.
  return best_scored ? `${attempted} · Best score ${best_correct} / ${best_scored}` : attempted;
}

function plural(count: number, word: string): string {
  return count === 1 ? word : `${word}s`;
}
