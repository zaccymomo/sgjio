import { Alert, ApiError, Button, Spinner, useAuth } from "@sgjio/ui";
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

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
  return (
    <div className="mx-auto flex max-w-lg flex-col gap-4 rounded-xl border border-line bg-white p-6">
      <div className="text-center">
        <p className="text-sm font-semibold text-brand">Your topic placements</p>
        <h1 className="mt-1 text-2xl font-bold text-ink">Your starting points are ready</h1>
        <p className="mt-2 text-sm text-muted">
          Introductory lessons at or below each placement are marked exempted.
        </p>
      </div>
      <ul className="divide-y divide-line rounded-lg border border-line">
        {result.placements.map((placement) => (
          <li key={placement.topic_id} className="flex items-center justify-between p-3 text-sm">
            <span className="font-medium text-ink">{placement.topic}</span>
            <span className="font-semibold text-brand">
              {placement.level === 0 ? "No exemptions" : `Level ${placement.level}`}
            </span>
          </li>
        ))}
      </ul>
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
