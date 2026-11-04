import { Alert, ApiError, Button, Spinner } from "@sgjio/ui";
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { aptitudeApi, type QuizQuestion, type QuizResult } from "../lib/aptitude";

export function AptitudeIntroPage() {
  const navigate = useNavigate();
  const [busy, setBusy] = useState<"start" | "skip" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = async (which: "start" | "skip") => {
    setBusy(which);
    setError(null);
    try {
      if (which === "skip") {
        await aptitudeApi.skip();
        navigate("/", { replace: true });
      } else navigate("/aptitude/quiz");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Please try again.");
      setBusy(null);
    }
  };
  return (
    <div className="mx-auto flex max-w-lg flex-col gap-4 rounded-xl border border-line bg-white p-6">
      <div>
        <p className="text-xs font-semibold tracking-wide text-brand uppercase">
          Your starting level
        </p>
        <h1 className="mt-1 text-2xl font-bold text-ink">How well do you know Singapore?</h1>
        <p className="mt-2 text-sm text-muted">
          Answer 5 short questions — one at each level. We use your result to suggest lessons that
          fit what you already know.
        </p>
      </div>
      {error && <Alert tone="error">{error}</Alert>}
      <Button loading={busy === "start"} onClick={() => void run("start")}>
        Take the 5-question quiz
      </Button>
      <Button variant="secondary" loading={busy === "skip"} onClick={() => void run("skip")}>
        Skip for now
      </Button>
      <p className="text-center text-xs text-muted">
        You can take or retake it later from your home page.
      </p>
    </div>
  );
}

export function AptitudeQuizPage() {
  const navigate = useNavigate();
  const [questions, setQuestions] = useState<QuizQuestion[] | null>(null);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  useEffect(() => {
    aptitudeApi
      .start()
      .then((data) => setQuestions(data.questions))
      .catch((cause: unknown) =>
        setError(cause instanceof ApiError ? cause.message : "The quiz could not be started."),
      );
  }, []);
  if (error && !questions)
    return (
      <div className="mx-auto max-w-lg">
        <Alert tone="error">{error}</Alert>
        <Link className="mt-4 inline-block text-sm font-semibold text-brand" to="/aptitude">
          Back
        </Link>
      </div>
    );
  if (!questions)
    return (
      <div className="flex justify-center py-16 text-brand">
        <Spinner className="size-6" label="Preparing your questions" />
      </div>
    );
  const question = questions[index];
  const chosen = answers[question.id];
  const next = async () => {
    if (!chosen) {
      setError("Choose an answer to continue.");
      return;
    }
    setError(null);
    if (index < questions.length - 1) {
      setIndex(index + 1);
      return;
    }
    setSubmitting(true);
    try {
      const result = await aptitudeApi.submit(
        questions.map((item) => ({ question_id: item.id, option_id: answers[item.id] })),
      );
      navigate("/aptitude/results", { replace: true, state: { result } });
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Your answers could not be saved.");
      setSubmitting(false);
    }
  };
  return (
    <div className="mx-auto flex max-w-lg flex-col gap-4">
      <div className="flex items-center justify-between text-sm">
        <span className="font-semibold text-ink">Question {index + 1} of 5</span>
        <span className="text-muted">
          {question.topic} · Level {question.level}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-line">
        <div
          className="h-full bg-brand transition-all"
          style={{ width: `${((index + 1) / 5) * 100}%` }}
        />
      </div>
      <section className="rounded-xl border border-line bg-white p-5">
        <h1 className="text-xl font-bold text-ink">{question.prompt}</h1>
        <div className="mt-4 flex flex-col gap-2">
          {question.options.map((option) => (
            <label
              key={option.id}
              className={`flex cursor-pointer items-center gap-3 rounded-lg border p-3 text-sm ${chosen === option.id ? "border-brand bg-brand-soft" : "border-line"}`}
            >
              <input
                type="radio"
                name={question.id}
                checked={chosen === option.id}
                onChange={() => setAnswers({ ...answers, [question.id]: option.id })}
              />
              {option.text}
            </label>
          ))}
        </div>
      </section>
      {error && <Alert tone="error">{error}</Alert>}
      <Button loading={submitting} onClick={() => void next()}>
        {index === 4 ? "See my result" : "Next question"}
      </Button>
      <p className="text-center text-xs text-muted">
        Answers are checked only after all five are submitted.
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
        .latest()
        .then(setResult)
        .catch(() => setError("No aptitude result is available yet."));
  }, [stateResult]);
  if (error) return <Alert tone="error">{error}</Alert>;
  if (!result)
    return (
      <div className="flex justify-center py-16 text-brand">
        <Spinner className="size-6" label="Loading your result" />
      </div>
    );
  return (
    <div className="mx-auto flex max-w-lg flex-col gap-4 rounded-xl border border-line bg-white p-6 text-center">
      <p className="text-sm font-semibold text-brand">Your starting point</p>
      <h1 className="text-4xl font-bold text-ink">Level {result.level}</h1>
      <p className="text-sm text-muted">
        You answered {result.correct} of {result.total} questions correctly. Your home page now
        shows lessons and a suggestion for Level {result.level}.
      </p>
      <Link
        to="/"
        className="flex h-11 items-center justify-center rounded-sm bg-ink px-4 text-sm font-semibold text-white"
      >
        Go to my lessons
      </Link>
      <Link to="/aptitude" className="text-sm font-semibold text-brand">
        Retake quiz
      </Link>
    </div>
  );
}
