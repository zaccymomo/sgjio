import { Alert, ErrorState, ProgressRing, Spinner, cn } from "@sgjio/ui";
import { readingLabel } from "@sgjio/ui/lesson";
import { Check, ChevronLeft, ChevronRight } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { type Topic, type TopicLesson, useTopic } from "../lib/topic";

/**
 * A topic opened from its progress circle (SCRUM-43 AC9): its lessons in the order
 * administrators set, each marked completed or not (SCRUM-53).
 *
 * Selecting a lesson opens it (AC2). The lesson says it came from here, so finishing or
 * closing it steps back to this page rather than stacking a second copy on top (AC3); that
 * keeps the browser's back button, like the "All topics" link, leading home (AC4).
 *
 * Whether each completed lesson's result was right is SCRUM-54; the API already sends it.
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
  const { name, completed, available, lessons } = topic;
  const questions = lessons.reduce((total, lesson) => total + lesson.questions, 0);

  return (
    <>
      <h1 className="text-[22px] font-bold text-ink">{name}</h1>

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
  const meta = completed ? "Completed" : openMeta(lesson);

  return (
    <Link
      to={`/lessons/${id}`}
      // Tells the lesson it can step back to this page when it closes (AC3, AC4).
      state={{ fromTopic: true }}
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

/** "About 2 min · 1 quiz question", timed as the lesson's cover times it. */
function openMeta({ reading_seconds, questions }: TopicLesson): string {
  return `${readingLabel(reading_seconds)} · ${questions} quiz ${plural(questions, "question")}`;
}

function plural(count: number, word: string): string {
  return count === 1 ? word : `${word}s`;
}
