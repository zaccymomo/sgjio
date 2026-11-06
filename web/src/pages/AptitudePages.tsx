import { Alert, ApiError, Button, Spinner, useAuth } from "@sgjio/ui";
import { ChevronDown, ChevronLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { TopicRadar } from "../components/TopicRadar";
import { aptitudeApi, type QuizAnswer, type QuizQuestion, type QuizResult } from "../lib/aptitude";

export function AptitudeIntroPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
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
        <h1 className="text-2xl font-bold text-ink">No aptitude test needed</h1>
        <p className="text-sm text-muted">The aptitude test is for Newcomers.</p>
        <Button onClick={() => navigate("/", { replace: true })}>Go to my lessons</Button>
      </div>
    );
  }

  if (completed) {
    return (
      <div className="mx-auto flex max-w-lg flex-col gap-4 rounded-xl border border-line bg-white p-6">
        <h1 className="text-2xl font-bold text-ink">Aptitude test already completed</h1>
        <p className="text-sm text-muted">
          Your starting point for each topic has been saved. The aptitude test can only be taken
          once during this version of SGJio.
        </p>
        <Link
          className="text-sm font-semibold text-brand"
          to="/aptitude/results"
          state={{ back: { label: "Back" } }}
        >
          View my topic placements
        </Link>
        <Button onClick={() => navigate("/", { replace: true })}>Go to my lessons</Button>
      </div>
    );
  }

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
      <Button onClick={() => navigate("/aptitude/quiz")}>Take the aptitude test now</Button>
      {/* SCRUM-98: nothing is stored for a skip, so this only leaves the page. Home keeps
          offering the test for as long as there is no completed attempt. */}
      <Button variant="secondary" onClick={() => navigate("/", { replace: true })}>
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
        setError(
          cause instanceof ApiError ? cause.message : "The aptitude test could not be started.",
        ),
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
      <p className="text-sm text-muted">
        If you don’t know, choose “I’m not sure” instead of guessing. A lucky guess could mark
        lessons as done that you would find useful.
      </p>
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

/** Where a link to the results came from, so the page can offer a way back (SCRUM-100). */
type ResultsBack = { label: string };

export function AptitudeResultsPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const state = location.state as { result?: QuizResult; back?: ResultsBack } | null;
  const stateResult = state?.result;
  const [result, setResult] = useState<QuizResult | null>(stateResult ?? null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!stateResult)
      aptitudeApi
        .result()
        .then(setResult)
        .catch(() => setError("No result is available yet."));
  }, [stateResult]);

  // Opened from "See why" on Home or a topic page: step back there. Straight after the
  // aptitude test there is nowhere to go back to, so "Go to my lessons" is the way on.
  const back = state?.back && (
    <button
      type="button"
      onClick={() => navigate(-1)}
      className="inline-flex w-fit cursor-pointer items-center gap-1 rounded-sm text-sm font-medium text-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
    >
      <ChevronLeft className="size-4" aria-hidden />
      {state.back.label}
    </button>
  );

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
    <div className="flex flex-col gap-4">
      {back}
      <div className="mx-auto flex w-full max-w-lg flex-col gap-4 rounded-xl border border-line bg-white p-6">
        <div className="text-center">
          <p className="text-sm font-semibold text-brand">Your topic placements</p>
          <h1 className="mt-1 text-2xl font-bold text-ink">Your starting points are ready</h1>
          <p className="mt-2 text-sm text-muted">
            Introductory lessons at or below each placement are marked exempted.
          </p>
          {available > 0 && (
            <p className="mt-1 text-sm text-muted">
              The aptitude test exempted you from{" "}
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
        <p className="text-center text-xs text-muted">The aptitude test cannot be retaken.</p>
      </div>
    </div>
  );
}

type Placement = QuizResult["placements"][number];

/**
 * One topic in the results (SCRUM-100): how many of its lessons the aptitude test exempted
 * (AC1), or that the learner starts from its first lesson (AC2). The topic's name opens it,
 * and a dropdown beneath lists the lessons exempted, each opening that lesson.
 */
function PlacementRow({ placement }: { placement: Placement }) {
  const { topic_id, topic, level, exempted, available, lessons } = placement;

  const [count, detail] =
    available === 0
      ? ["No lessons yet", "Its lessons will appear when they're published"]
      : exempted === 0
        ? ["None exempted", "Start from the first lesson"]
        : exempted === available
          ? ["All lessons exempted", `Up to Level ${level}`]
          : [
              `${exempted} ${exempted === 1 ? "lesson" : "lessons"} exempted`,
              `Up to Level ${level}`,
            ];

  // The name and its detail on the left, the count centred against both on the right.
  return (
    <li className="flex flex-col gap-2 p-3 text-sm">
      <div className="flex items-center justify-between gap-3">
        <span className="flex min-w-0 flex-col gap-0.5">
          <Link
            to={`/topics/${topic_id}`}
            className="w-fit rounded-sm font-medium text-ink underline-offset-2 hover:text-brand hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          >
            {topic}
          </Link>
          <span className="text-caption text-muted">{detail}</span>
        </span>
        <span className="shrink-0 text-right font-semibold text-brand">{count}</span>
      </div>
      {lessons.length > 0 && (
        <details className="group">
          <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded-sm text-caption font-semibold text-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand [&::-webkit-details-marker]:hidden">
            <ChevronDown
              className="size-3.5 transition-transform group-open:rotate-180"
              aria-hidden
            />
            <span className="group-open:hidden">Show exempted lessons</span>
            <span className="hidden group-open:inline">Hide exempted lessons</span>
          </summary>
          <ul className="mt-2 flex flex-col gap-1.5 border-l-2 border-line pl-3">
            {lessons.map((lesson) => (
              <li key={lesson.id} className="flex items-baseline justify-between gap-3">
                <Link
                  to={`/lessons/${lesson.id}`}
                  className="rounded-sm text-ink underline-offset-2 hover:text-brand hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
                >
                  {lesson.title}
                </Link>
                <span className="shrink-0 text-caption text-subtle">Level {lesson.level}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </li>
  );
}
