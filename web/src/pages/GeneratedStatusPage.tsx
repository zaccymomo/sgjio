import { Alert, ApiError, Button, ErrorState, Spinner, apiFetch, cn } from "@sgjio/ui";
import { readingLabel } from "@sgjio/ui/lesson";
import { ArrowRight, Check, ChevronLeft, CircleAlert, Sparkles, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { MadeWithAi } from "../components/MadeWithAi";
import {
  DIFFICULTY_LABELS,
  FOCUS_LABELS,
  LENGTH_TIME,
  WAITING,
  choicesOf,
  dailyLimitMessage,
  errorMessage,
  isDailyLimit,
  plural,
  startGeneration,
  useGenerateOptions,
  type GeneratedStatus,
} from "../lib/generated";

const POLL_MS = 1500;

const focusRing =
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand";

type State =
  | { status: "loading" }
  | { status: "ready"; generated: GeneratedStatus }
  | { status: "error"; message: string };

/**
 * One generated lesson (docs/ai-lessons-plan.md, steps 4 and 6): "Preparing your lesson…"
 * while it is written, checked every 1.5 seconds, then the lesson's preview, or why it
 * failed. A cancelled one goes back to Practice.
 */
export function GeneratedStatusPage() {
  const { id = "" } = useParams();
  // Keyed so that "Generate again" starts the new request from "loading".
  return <StatusView key={id} id={id} />;
}

function StatusView({ id }: { id: string }) {
  const navigate = useNavigate();
  const [state, setState] = useState<State>({ status: "loading" });
  const [tries, setTries] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;
    let seen = false;
    async function poll() {
      try {
        const generated = await apiFetch<GeneratedStatus>(`/api/generate/${id}`, {
          signal: controller.signal,
        });
        seen = true;
        setState({ status: "ready", generated });
        if (WAITING.includes(generated.status)) timer = window.setTimeout(poll, POLL_MS);
      } catch (error) {
        if (controller.signal.aborted) return;
        // A dropped check while waiting just tries again; only the first load reports it.
        if (seen) {
          timer = window.setTimeout(poll, POLL_MS);
          return;
        }
        const missing = error instanceof ApiError && error.status === 404;
        setState({
          status: "error",
          message: missing
            ? "We couldn't find this lesson."
            : errorMessage(error, "We couldn't load this lesson. Check your connection."),
        });
      }
    }
    void poll();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [id, tries]);

  const cancelled = state.status === "ready" && state.generated.status === "cancelled";
  useEffect(() => {
    if (cancelled) navigate("/practice", { replace: true });
  }, [cancelled, navigate]);

  if (state.status === "loading" || cancelled) {
    return (
      <div className="flex justify-center py-16 text-brand">
        <Spinner className="size-6" label="Loading your lesson" />
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div className="flex flex-col gap-4">
        <BackLink />
        <ErrorState
          message={state.message}
          onRetry={() => {
            setState({ status: "loading" });
            setTries((n) => n + 1);
          }}
        />
      </div>
    );
  }

  const { generated } = state;
  if (generated.status === "ready" && generated.lesson) return <Ready generated={generated} />;
  if (generated.status === "failed") return <Failed generated={generated} />;
  return (
    <Generating
      generated={generated}
      onCancelled={(next) => setState({ status: "ready", generated: next })}
    />
  );
}

function BackLink() {
  return (
    <Link
      to="/practice"
      className={cn(
        "inline-flex w-fit items-center gap-1 rounded-sm text-sm font-medium text-muted hover:text-ink",
        focusRing,
      )}
    >
      <ChevronLeft className="size-4" aria-hidden />
      Practice
    </Link>
  );
}

/** The daily limit, for "today's 3"; 3 (D14) until the options have loaded. */
function useDailyLimit() {
  const { state } = useGenerateOptions();
  return state.status === "ready" ? state.options.daily_limit : 3;
}

/** "Generate again" and "Try again": the same choices, as a new request. */
function useAgain(generated: GeneratedStatus) {
  const navigate = useNavigate();
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [limited, setLimited] = useState(false);

  async function again() {
    setSending(true);
    setError(null);
    try {
      const created = await startGeneration(choicesOf(generated));
      navigate(`/practice/generated/${created.id}`);
    } catch (failure) {
      setSending(false);
      if (isDailyLimit(failure)) setLimited(true);
      else
        setError(errorMessage(failure, "We couldn't start a new lesson. Check your connection."));
    }
  }

  function changeOptions() {
    navigate("/practice/generate", { state: { choices: choicesOf(generated) } });
  }

  return { again, changeOptions, sending, error, limited };
}

function Chip({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-full border border-line bg-surface px-2.5 py-1 text-caption font-medium text-muted">
      {children}
    </span>
  );
}

const STEPS = [
  "Choosing a scenario",
  "Writing cards and questions",
  "Checking answers and wording",
];
const CURRENT_STEP = { requested: 0, writing: 1, checking: 2 } as const;

function Generating({
  generated,
  onCancelled,
}: {
  generated: GeneratedStatus;
  onCancelled: (next: GeneratedStatus) => void;
}) {
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const current = CURRENT_STEP[generated.status as keyof typeof CURRENT_STEP] ?? 0;

  async function cancel() {
    setCancelling(true);
    setError(null);
    try {
      onCancelled(
        await apiFetch<GeneratedStatus>(`/api/generate/${generated.id}/cancel`, {
          method: "POST",
        }),
      );
    } catch (failure) {
      setCancelling(false);
      setError(errorMessage(failure, "We couldn't cancel it. Check your connection."));
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center gap-2">
        <Link
          to="/practice"
          aria-label="Back to Practice"
          className={cn(
            "flex size-9 shrink-0 items-center justify-center rounded-full text-muted hover:bg-ink/5 hover:text-ink",
            focusRing,
          )}
        >
          <X className="size-5" aria-hidden />
        </Link>
        <h1 className="min-w-0 truncate text-base font-semibold text-ink">
          New {generated.topic.name} lesson
        </h1>
        <MadeWithAi />
      </div>

      <div className="flex flex-col items-center gap-3 pt-4 text-center">
        <span className="flex size-20 items-center justify-center rounded-full bg-brand-soft">
          <span className="flex size-12 items-center justify-center rounded-full bg-brand text-white">
            <Sparkles className="size-6" aria-hidden />
          </span>
        </span>
        <p role="status" className="text-lg font-bold text-ink">
          Preparing your lesson…
        </p>
        <p className="max-w-xs text-sm text-muted">
          This usually takes under a minute. You may leave this page; your lesson will appear in
          Practice.
        </p>
        <div className="flex flex-wrap justify-center gap-1.5">
          <Chip>{generated.topic.name}</Chip>
          <Chip>{FOCUS_LABELS[generated.focus]}</Chip>
          <Chip>{DIFFICULTY_LABELS[generated.difficulty]}</Chip>
          <Chip>{LENGTH_TIME[generated.length]}</Chip>
        </div>
      </div>

      <ol className="mx-auto flex w-full max-w-sm flex-col gap-3 rounded-lg border border-line bg-white p-4">
        {STEPS.map((step, n) => {
          const done = n < current;
          const active = n === current;
          const label = n === 0 && generated.ask ? `${step} based on your request` : step;
          return (
            <li key={step} className="flex items-center gap-3 text-sm">
              {done ? (
                <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-success text-white">
                  <Check className="size-3.5" aria-hidden />
                </span>
              ) : active ? (
                <span
                  className="size-5 shrink-0 animate-spin rounded-full border-2 border-brand/20 border-t-brand"
                  aria-hidden
                />
              ) : (
                <span className="size-5 shrink-0 rounded-full border-2 border-line" aria-hidden />
              )}
              <span
                className={cn(
                  done || active ? "text-ink" : "text-subtle",
                  active && "font-semibold",
                )}
              >
                {label}
                <span className="sr-only">{done ? " (done)" : active ? " (in progress)" : ""}</span>
              </span>
            </li>
          );
        })}
      </ol>

      <div className="mx-auto flex w-full max-w-sm flex-col gap-2" aria-hidden>
        <div className="h-4 w-2/3 animate-pulse rounded-sm bg-line" />
        <div className="h-3 w-full animate-pulse rounded-sm bg-line/70" />
        <div className="h-3 w-5/6 animate-pulse rounded-sm bg-line/70" />
      </div>

      {error && <Alert tone="error">{error}</Alert>}

      <div className="mx-auto flex w-full max-w-sm flex-col gap-2">
        <Link
          to="/practice"
          className={cn(
            "flex h-11 items-center justify-center rounded-sm border border-line bg-white px-4 text-sm font-semibold text-ink hover:bg-surface",
            focusRing,
          )}
        >
          Back to Practice
        </Link>
        <Button
          variant="ghost"
          loading={cancelling}
          onClick={() => void cancel()}
          className="text-brand hover:text-brand"
        >
          Cancel this lesson
        </Button>
      </div>
    </div>
  );
}

function Ready({ generated }: { generated: GeneratedStatus }) {
  const lesson = generated.lesson!;
  const { again, changeOptions, sending, error, limited } = useAgain(generated);
  const limit = useDailyLimit();

  return (
    <div className="flex flex-col gap-4">
      <BackLink />
      <div className="flex flex-col items-start gap-2">
        <MadeWithAi />
        <h1 className="text-[22px] font-bold text-ink">{lesson.title}</h1>
        <div className="flex flex-wrap gap-1.5">
          <Chip>{generated.topic.name}</Chip>
          <Chip>{plural(lesson.cards, "card", "cards")}</Chip>
          <Chip>{plural(lesson.questions, "quiz question", "quiz questions")}</Chip>
          <Chip>{readingLabel(lesson.reading_seconds)}</Chip>
        </div>
      </div>

      <section className="rounded-lg border border-line bg-surface p-4">
        <h2 className="text-caption font-semibold tracking-wide text-muted uppercase">
          Why this lesson
        </h2>
        <div className="mt-2 flex flex-col gap-2 text-sm text-ink">
          {generated.covers.length > 0 && (
            <div>
              <p>Based on questions you answered incorrectly:</p>
              <ul className="mt-1 list-disc pl-5">
                {generated.covers.map((cover) => (
                  <li key={`${cover.lesson_id}-${cover.correct}`}>
                    {cover.correct} · <span className="text-muted">{cover.lesson_title}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {generated.ask && (
            <p>
              {generated.covers.length > 0 ? "You also asked about" : "You asked about"}:{" "}
              <span className="italic">{generated.ask}</span>
            </p>
          )}
          {generated.covers.length === 0 && !generated.ask && (
            <p>
              New material in {generated.topic.name} at Level {generated.level}.
            </p>
          )}
        </div>
      </section>

      {lesson.learning_points.length > 0 && (
        <section>
          <h2 className="text-caption font-semibold tracking-wide text-muted uppercase">
            What you will learn
          </h2>
          <ul className="mt-2 flex flex-col gap-2">
            {lesson.learning_points.map((point) => (
              <li key={point} className="flex items-start gap-2 text-sm text-ink">
                <Check className="mt-0.5 size-4 shrink-0 text-brand" aria-hidden />
                {point}
              </li>
            ))}
          </ul>
        </section>
      )}

      <Alert tone="warning">
        This lesson was written by AI and has not been reviewed by our team. If anything looks
        incorrect, select the flag on that card to report it.
      </Alert>

      {error && <Alert tone="error">{error}</Alert>}
      {(limited || generated.left_today <= 0) && <Alert>{dailyLimitMessage(limit)}</Alert>}

      <div className="flex flex-col gap-2">
        <Link
          to={`/generated/${generated.id}/play`}
          state={{ from: "status" }}
          className={cn(
            "flex h-12 items-center justify-center gap-2 rounded-sm bg-ink px-4 text-base font-semibold text-white hover:bg-ink/90",
            focusRing,
          )}
        >
          Start lesson
          <ArrowRight className="size-4" aria-hidden />
        </Link>
        <div className="grid grid-cols-2 gap-2">
          <Button variant="secondary" onClick={changeOptions}>
            Change options
          </Button>
          <Button
            variant="secondary"
            loading={sending}
            disabled={limited || generated.left_today <= 0}
            onClick={() => void again()}
          >
            Generate again
          </Button>
        </div>
        <p className="text-center text-caption text-muted">Saved to Practice.</p>
      </div>
    </div>
  );
}

function Failed({ generated }: { generated: GeneratedStatus }) {
  const { again, changeOptions, sending, error, limited } = useAgain(generated);
  const limit = useDailyLimit();
  const offTopic = generated.failure?.code === "off_topic";
  const message = generated.failure?.message ?? "Please try again shortly.";

  return (
    <div className="flex flex-col gap-4">
      <BackLink />
      <div className="flex flex-col items-center gap-3 pt-6 text-center">
        <span className="flex size-14 items-center justify-center rounded-full bg-danger-soft text-danger">
          <CircleAlert className="size-7" aria-hidden />
        </span>
        <h1 className="max-w-sm text-lg font-bold text-ink">We couldn&apos;t create this lesson</h1>
        <p className="max-w-sm text-sm text-muted">{message}</p>
      </div>

      {error && <Alert tone="error">{error}</Alert>}
      {limited && <Alert>{dailyLimitMessage(limit)}</Alert>}

      <div className="mx-auto grid w-full max-w-sm grid-cols-2 gap-2">
        <Button variant={offTopic ? "accent" : "secondary"} onClick={changeOptions}>
          Change options
        </Button>
        <Button
          variant={offTopic ? "secondary" : "accent"}
          loading={sending}
          disabled={limited}
          onClick={() => void again()}
        >
          Try again
        </Button>
      </div>
    </div>
  );
}
