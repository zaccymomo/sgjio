import { Alert, ApiError, Button, Spinner, cn, useAuth } from "@sgjio/ui";
import { ChevronDown } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { LessonMark } from "../components/LessonMark";
import { TopicRadar } from "../components/TopicRadar";
import { useTopic } from "../lib/topic";
import { aptitudeApi, type QuizAnswer, type QuizQuestion, type QuizResult } from "../lib/aptitude";

export function AptitudeIntroPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState<"start" | "skip" | null>(null);
  const [completed, setCompleted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (user?.user_type !== "newcomer") return;
    aptitudeApi
      .result()
      .then(() => setCompleted(true))
      .catch((cause: unknown) => {
        if (!(cause instanceof ApiError) || cause.status !== 404) {
          setError(cause instanceof ApiError ? cause.message : "Please try again.");
        }
      });
  }, [user?.user_type]);

  if (user?.user_type !== "newcomer") {
    return (
      <div className="mx-auto flex max-w-lg flex-col gap-4 rounded-xl border border-line bg-white p-6">
        <h1 className="text-2xl font-bold text-ink">No placement quiz needed</h1>
        <p className="text-sm text-muted">The onboarding aptitude quiz is for Newcomers.</p>
        <Button onClick={() => navigate("/", { replace: true })}>Go to my lessons</Button>
      </div>
    );
  }

  if (completed) {
    return (
      <div className="mx-auto flex max-w-lg flex-col gap-4 rounded-xl border border-line bg-white p-6">
        <h1 className="text-2xl font-bold text-ink">Quiz already completed</h1>
        <p className="text-sm text-muted">
          Your starting point for each topic has been saved. The onboarding quiz can only be taken
          once during this version of SGJio.
        </p>
        <Link className="text-sm font-semibold text-brand" to="/aptitude/results">
          View my topic placements
        </Link>
        <Button onClick={() => navigate("/", { replace: true })}>Go to my lessons</Button>
      </div>
    );
  }

  const run = async (which: "start" | "skip") => {
    setBusy(which);
    setError(null);
    try {
      if (which === "skip") {
        await aptitudeApi.skip();
        navigate("/", { replace: true });
      } else {
        navigate("/aptitude/quiz");
      }
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Please try again.");
      setBusy(null);
    }
  };

  return (
    <div className="mx-auto flex max-w-lg flex-col gap-4 rounded-xl border border-line bg-white p-6">
      <div>
        <p className="text-xs font-semibold tracking-wide text-brand uppercase">Topic placement</p>
        <h1 className="mt-1 text-2xl font-bold text-ink">Find your starting point</h1>
        <p className="mt-2 text-sm text-muted">
          SGJio checks each cultural topic separately. Every topic starts at Level 1. Correct
          answers move you up; the first wrong answer moves you to the next topic. Lessons below
          your result are marked exempted.
        </p>
      </div>
      {error && <Alert tone="error">{error}</Alert>}
      <Button loading={busy === "start"} onClick={() => void run("start")}>
        Take the quiz now
      </Button>
      <Button variant="secondary" loading={busy === "skip"} onClick={() => void run("skip")}>
        Skip for now
      </Button>
      <p className="text-center text-xs text-muted">
        If you leave before finishing, no result is saved and you can restart.
      </p>
    </div>
  );
}

export function AptitudeQuizPage() {
  const navigate = useNavigate();
  const [question, setQuestion] = useState<QuizQuestion | null>(null);
  const [answers, setAnswers] = useState<QuizAnswer[]>([]);
  const [chosen, setChosen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    aptitudeApi
      .start()
      .then((step) => setQuestion(step.question))
      .catch((cause: unknown) =>
        setError(cause instanceof ApiError ? cause.message : "The quiz could not be started."),
      );
  }, []);

  if (error && !question) {
    return (
      <div className="mx-auto max-w-lg">
        <Alert tone="error">{error}</Alert>
        <Link className="mt-4 inline-block text-sm font-semibold text-brand" to="/aptitude">
          Back
        </Link>
      </div>
    );
  }
  if (!question) {
    return (
      <div className="flex justify-center py-16 text-brand">
        <Spinner className="size-6" label="Preparing your questions" />
      </div>
    );
  }

  const next = async () => {
    if (!chosen) {
      setError("Choose an answer to continue.");
      return;
    }
    setError(null);
    setSubmitting(true);
    const nextAnswers = [...answers, { question_id: question.id, option_id: chosen }];
    try {
      const step = await aptitudeApi.next(nextAnswers);
      if (step.done) {
        const result = await aptitudeApi.submit(nextAnswers);
        navigate("/aptitude/results", { replace: true, state: { result } });
        return;
      }
      setAnswers(nextAnswers);
      setQuestion(step.question);
      setChosen(null);
      setSubmitting(false);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Your answer could not be saved.");
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto flex max-w-lg flex-col gap-4">
      <div className="flex items-center justify-between text-sm">
        <span className="font-semibold text-ink">
          Topic {question.topic_index} of {question.topic_count}: {question.topic}
        </span>
        <span className="text-muted">Level {question.level}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-line">
        <div
          className="h-full bg-brand transition-all"
          style={{ width: `${(question.topic_index / question.topic_count) * 100}%` }}
        />
      </div>
      <section className="rounded-xl border border-line bg-white p-5">
        <h1 className="text-xl font-bold text-ink">{question.prompt}</h1>
        <div className="mt-4 flex flex-col gap-2">
          {question.options.map((option) => (
            <label
              key={option.id}
              className={`flex cursor-pointer items-center gap-3 rounded-lg border p-3 text-sm ${
                chosen === option.id ? "border-brand bg-brand-soft" : "border-line"
              }`}
            >
              <input
                type="radio"
                name={question.id}
                checked={chosen === option.id}
                onChange={() => setChosen(option.id)}
              />
              {option.text}
            </label>
          ))}
        </div>
      </section>
      {error && <Alert tone="error">{error}</Alert>}
      <Button loading={submitting} onClick={() => void next()}>
        Continue
      </Button>
      <p className="text-center text-xs text-muted">
        You will see your placements after every topic is complete.
      </p>
    </div>
  );
}

export function AptitudeResultsPage() {
  const location = useLocation();
  const stateResult = (location.state as { result?: QuizResult } | null)?.result;
  const [result, setResult] = useState<QuizResult | null>(stateResult ?? null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!stateResult)
      aptitudeApi
        .result()
        .then(setResult)
        .catch(() => setError("No result is available yet."));
  }, [stateResult]);
  if (error) return <Alert tone="error">{error}</Alert>;
  if (!result) {
    return (
      <div className="flex justify-center py-16 text-brand">
        <Spinner className="size-6" label="Loading your result" />
      </div>
    );
  }
  const exempted = result.placements.reduce((total, placement) => total + placement.exempted, 0);
  const available = result.placements.reduce((total, placement) => total + placement.available, 0);
  return (
    <div className="mx-auto flex max-w-lg flex-col gap-4 rounded-xl border border-line bg-white p-6">
      <div className="text-center">
        <p className="text-sm font-semibold text-brand">Your topic placements</p>
        <h1 className="mt-1 text-2xl font-bold text-ink">Your starting points are ready</h1>
        <p className="mt-2 text-sm text-muted">
          Introductory lessons at or below each placement are marked exempted.
        </p>
        {available > 0 && (
          <p className="mt-1 text-sm text-muted">
            The quiz exempted you from{" "}
            <span className="font-semibold text-ink">
              {exempted} of {available} {available === 1 ? "lesson" : "lessons"}
            </span>
            . They already count in your topic circles.
          </p>
        )}
      </div>
      {/* SCRUM-100: the level in each topic as a shape; the list below says the same in
          words, with the counts. */}
      <TopicRadar
        topics={result.placements.map((placement) => ({
          id: placement.topic_id,
          name: placement.topic,
          level: placement.level,
        }))}
      />
      <ul className="divide-y divide-line rounded-lg border border-line">
        {result.placements.map((placement) => (
          <PlacementRow key={placement.topic_id} placement={placement} />
        ))}
      </ul>
      <p className="text-center text-xs text-muted">
        You can still open exempted lessons any time.
      </p>
      <Link
        to="/"
        className="flex h-11 items-center justify-center rounded-sm bg-ink px-4 text-sm font-semibold text-white"
      >
        Go to my lessons
      </Link>
      <p className="text-center text-xs text-muted">This onboarding quiz cannot be retaken.</p>
    </div>
  );
}

type Placement = QuizResult["placements"][number];

/**
 * One topic in the results (SCRUM-100): how many of its lessons the quiz exempted (AC1), or
 * that the learner starts from its first lesson (AC2). Selecting it opens the topic's
 * lessons in place, marked as on the topic page, with where to start.
 */
function PlacementRow({ placement }: { placement: Placement }) {
  const [open, setOpen] = useState(false);
  const { topic_id, topic, level, exempted, available } = placement;
  const panelId = `placement-${topic_id}`;

  const [count, detail] =
    available === 0
      ? ["No lessons yet", "Its lessons will appear when they're published"]
      : exempted === 0
        ? ["None exempted", "You'll start from the first lesson"]
        : exempted === available
          ? [`All ${available} exempted`, `Up to Level ${level}`]
          : [`${exempted} of ${available} exempted`, `Up to Level ${level}`];

  const summary = (
    <>
      <span className="flex min-w-0 flex-col">
        <span className="font-medium text-ink">{topic}</span>
        <span className="text-caption text-muted">{detail}</span>
      </span>
      <span className="flex shrink-0 items-center gap-1.5">
        <span className="font-semibold text-brand">{count}</span>
        {available > 0 && (
          <ChevronDown
            className={cn("size-4 text-subtle transition-transform", open && "rotate-180")}
            aria-hidden
          />
        )}
      </span>
    </>
  );

  return (
    <li className="text-sm">
      {available === 0 ? (
        <div className="flex items-center justify-between gap-3 p-3">{summary}</div>
      ) : (
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((value) => !value)}
          className={cn(
            "flex w-full items-center justify-between gap-3 p-3 text-left",
            "transition-colors hover:bg-surface",
            "focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand",
          )}
        >
          {summary}
        </button>
      )}
      {open && (
        <div id={panelId} className="border-t border-line bg-surface p-3">
          <PlacementLessons topicId={topic_id} />
        </div>
      )}
    </li>
  );
}

/** A topic's lessons, lowest level first as on its page, loaded when its row is opened. */
function PlacementLessons({ topicId }: { topicId: string }) {
  const { state, reload } = useTopic(topicId);

  if (state.status === "loading") {
    return (
      <div className="flex justify-center py-3 text-brand">
        <Spinner className="size-5" label="Loading this topic's lessons" />
      </div>
    );
  }
  if (state.status === "unavailable")
    return <p className="text-caption text-muted">{state.message}</p>;
  if (state.status === "error") {
    return (
      <p className="text-caption text-muted">
        {state.message}{" "}
        <button type="button" onClick={reload} className="font-semibold text-brand underline">
          Try again
        </button>
      </p>
    );
  }

  const { lessons } = state.topic;
  const start = lessons.find((lesson) => !lesson.completed && !lesson.exempted);
  return (
    <div className="flex flex-col gap-2">
      <ul className="flex flex-col gap-2">
        {lessons.map((lesson) => (
          <li key={lesson.id}>
            <Link
              to={`/lessons/${lesson.id}`}
              className={cn(
                "flex items-center gap-3 rounded-lg border bg-white px-3 py-2.5",
                lesson === start ? "border-ink" : "border-line",
                "transition-colors hover:border-brand/40 hover:bg-brand-soft/40",
                "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
              )}
            >
              <LessonMark completed={lesson.completed} exempted={lesson.exempted} />
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="text-sm font-semibold text-ink">{lesson.title}</span>
                <span className="text-caption text-subtle">
                  Level {lesson.level}
                  {lesson.completed ? " · Completed" : lesson.exempted ? " · Exempted" : ""}
                </span>
              </span>
              {lesson === start && (
                <span className="shrink-0 rounded-sm bg-brand-soft px-1.5 py-0.5 text-2xs font-semibold text-brand">
                  Start here
                </span>
              )}
            </Link>
          </li>
        ))}
      </ul>
      <Link
        to={`/topics/${topicId}`}
        className="self-start text-caption font-semibold text-brand hover:underline"
      >
        Open this topic
      </Link>
    </div>
  );
}
