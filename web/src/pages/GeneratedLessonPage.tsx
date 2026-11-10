import { ApiError, Button, ErrorState, FullPageSpinner, apiFetch, cn } from "@sgjio/ui";
import {
  LessonDeck,
  type Assets,
  type CheckResult,
  type DeckSummary,
  type LearnerCard,
} from "@sgjio/ui/lesson";
import { Check, ChevronLeft, Flag, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { MadeWithAi } from "../components/MadeWithAi";
import { ReportProblemDialog } from "../components/ReportProblemDialog";
import { errorMessage } from "../lib/generated";

/** GET /api/generated/{id}/lesson: the same shape as GET /api/lessons/{id}. */
type GeneratedLesson = {
  id: string;
  version: number;
  title: string;
  summary: string;
  topic: { id: string; name: string };
  reading_seconds: number;
  cards: LearnerCard[];
  assets: Assets;
};

type Score = { correct: number; scored: number };
type FinishResult = { attempt_id: string; score: Score; best: Score };

type Load =
  | { status: "loading" }
  | { status: "ready"; lesson: GeneratedLesson }
  | { status: "error"; message: string; retry: boolean };

type Save = { status: "idle" | "saving" | "saved" } | { status: "error"; message: string };

const focusRing =
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand";

/**
 * Playing an AI-generated lesson (docs/ai-lessons-plan.md, steps 7 and 8, D19): the same
 * deck as LessonPage, with a "Made with AI" badge, the flag posting to Learning, and an end
 * card that asks whether it was useful. Nothing here touches circles or progress.
 */
export function GeneratedLessonPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const fromStatus = (location.state as { from?: "status" } | null)?.from === "status";
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [save, setSave] = useState<Save>({ status: "idle" });
  const [reporting, setReporting] = useState<{ id: string; number: number } | null>(null);
  const [reportSent, setReportSent] = useState(false);
  const attempt = useRef<Promise<string> | null>(null);
  const finished = useRef<string | null>(null);

  const fetchLesson = useCallback(
    async (signal?: AbortSignal): Promise<Load | null> => {
      try {
        const lesson = await apiFetch<GeneratedLesson>(`/api/generated/${id}/lesson`, {
          signal,
        });
        return { status: "ready", lesson };
      } catch (error) {
        if (signal?.aborted) return null;
        const missing = error instanceof ApiError && error.status === 404;
        return {
          status: "error",
          message: missing
            ? "This lesson isn't available."
            : errorMessage(error, "We couldn't load this lesson. Check your connection."),
          retry: !missing,
        };
      }
    },
    [id],
  );

  useEffect(() => {
    const controller = new AbortController();
    void fetchLesson(controller.signal).then((next) => next && setLoad(next));
    return () => controller.abort();
  }, [fetchLesson]);

  useEffect(() => {
    if (!reportSent) return;
    const timer = window.setTimeout(() => setReportSent(false), 5000);
    return () => window.clearTimeout(timer);
  }, [reportSent]);

  const ensureAttempt = useCallback(() => {
    attempt.current ??= apiFetch<{ id: string }>(`/api/generated/${id}/attempts`, {
      method: "POST",
    }).then(
      (created) => created.id,
      (error: unknown) => {
        attempt.current = null;
        throw error;
      },
    );
    return attempt.current;
  }, [id]);

  const check = useCallback(
    async (questionId: string, optionId: string) => {
      const attemptId = await ensureAttempt();
      return apiFetch<CheckResult>(`/api/generated/attempts/${attemptId}/answers`, {
        method: "POST",
        body: { question_id: questionId, option_id: optionId },
      });
    },
    [ensureAttempt],
  );

  const finish = useCallback(async () => {
    if (!attempt.current) return;
    setSave({ status: "saving" });
    try {
      const attemptId = await attempt.current;
      await apiFetch<FinishResult>(`/api/generated/attempts/${attemptId}/finish`, {
        method: "POST",
      });
      finished.current = attemptId;
      setSave({ status: "saved" });
    } catch (error) {
      setSave({
        status: "error",
        message: errorMessage(error, "We couldn't save your score. Check your connection."),
      });
    }
  }, []);

  const onFinish = useCallback(() => {
    void attempt.current?.then((attemptId) => {
      if (finished.current !== attemptId) void finish();
    });
  }, [finish]);

  const backToStatus = useCallback(() => {
    // Opened from its Ready screen: step back to it, so history stays Practice -> lesson.
    if (fromStatus) return navigate(-1);
    navigate(`/practice/generated/${id}`, { replace: true });
  }, [fromStatus, id, navigate]);

  if (load.status === "loading") return <FullPageSpinner />;
  if (load.status === "error") {
    return (
      <div className="flex min-h-dvh flex-col bg-white px-4 py-6">
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
        <ErrorState
          message={load.message}
          onRetry={
            load.retry
              ? () => {
                  setLoad({ status: "loading" });
                  void fetchLesson().then((next) => next && setLoad(next));
                }
              : undefined
          }
        />
      </div>
    );
  }

  const { lesson } = load;

  function renderEnd(summary: DeckSummary, restart: () => void) {
    return (
      <>
        {summary.scored > 0 && (
          <p className="text-center text-base font-semibold text-ink">
            {summary.correct} of {summary.scored} right first try
          </p>
        )}
        <p className="text-center text-sm text-muted">
          Generated lessons do not affect your progress.
        </p>
        <p role="status" className="min-h-5 text-center text-sm text-muted">
          {save.status === "saving" && "Saving your score…"}
          {save.status === "error" && <span className="text-danger">{save.message}</span>}
        </p>
        {save.status === "error" && (
          <Button variant="secondary" onClick={() => void finish()}>
            Try saving again
          </Button>
        )}
        <RatingCard id={id} />
        <Link
          to="/practice/generate"
          className={cn(
            "flex h-14 w-full items-center justify-center rounded-2xl bg-brand text-base font-bold text-white hover:bg-brand/90",
            focusRing,
          )}
        >
          Generate another lesson
        </Link>
        <Link
          to="/practice"
          className={cn(
            "flex h-12 w-full items-center justify-center rounded-2xl border border-line bg-white text-base font-semibold text-ink hover:bg-surface",
            focusRing,
          )}
        >
          Back to Practice
        </Link>
        <button
          type="button"
          onClick={() => {
            attempt.current = null;
            finished.current = null;
            setSave({ status: "idle" });
            restart();
          }}
          className={cn(
            "flex h-12 w-full items-center justify-center gap-2 rounded-2xl text-base font-semibold text-muted hover:bg-ink/5 hover:text-ink",
            focusRing,
          )}
        >
          <RotateCcw className="size-5" aria-hidden />
          Retake lesson
        </button>
      </>
    );
  }

  return (
    <div className="relative h-dvh">
      <LessonDeck
        lesson={{
          title: lesson.title,
          summary: lesson.summary,
          topicName: lesson.topic.name,
          readingSeconds: lesson.reading_seconds,
        }}
        cards={lesson.cards}
        assets={lesson.assets}
        check={check}
        onExit={backToStatus}
        onFinish={onFinish}
        renderEnd={renderEnd}
        badge={<MadeWithAi />}
        cardActions={(card) => (
          <button
            type="button"
            onClick={() => {
              setReportSent(false);
              setReporting({ id: card.id, number: lesson.cards.indexOf(card) + 1 });
            }}
            aria-label="Report a problem with this card"
            title="Report a problem"
            className="flex size-9 shrink-0 items-center justify-center rounded-full text-muted transition-colors hover:bg-ink/5 hover:text-ink focus-visible:outline-2 focus-visible:outline-brand"
          >
            <Flag className="size-5" aria-hidden />
          </button>
        )}
      />
      <ReportProblemDialog
        open={reporting !== null}
        lessonId={lesson.id}
        version={lesson.version}
        cardId={reporting?.id ?? ""}
        cardNumber={reporting?.number ?? 0}
        reportPath={`/api/generated/${id}/reports`}
        onClose={() => setReporting(null)}
        onSent={() => {
          setReporting(null);
          setReportSent(true);
        }}
      />
      <div
        role="status"
        className="pointer-events-none absolute inset-x-0 top-16 z-20 flex justify-center px-4"
      >
        {reportSent && (
          <p className="flex items-center gap-2 rounded-full bg-ink px-4 py-2 text-sm font-medium text-white shadow-lg">
            <Check className="size-4" aria-hidden />
            Thanks, your report has been sent.
          </p>
        )}
      </div>
    </div>
  );
}

const REASONS = {
  yes: [
    { value: "right_level", label: "Right level" },
    { value: "clear", label: "Clear explanations" },
    { value: "more_like_this", label: "More like this" },
  ],
  no: [
    { value: "too_easy", label: "Too easy" },
    { value: "too_hard", label: "Too hard" },
    { value: "not_relevant", label: "Not relevant to me" },
    { value: "something_wrong", label: "Contains an error" },
  ],
} as const;

const SAVE_DELAY_MS = 600;

/** "Was this lesson useful?": saved with POST /api/generated/{id}/rating on each change. */
function RatingCard({ id }: { id: string }) {
  const [useful, setUseful] = useState<boolean | null>(null);
  const [reasons, setReasons] = useState<string[]>([]);
  const [saved, setSaved] = useState<"idle" | "saved" | "error">("idle");

  useEffect(() => {
    if (useful === null) return;
    const timer = window.setTimeout(() => {
      apiFetch(`/api/generated/${id}/rating`, { method: "POST", body: { useful, reasons } }).then(
        () => setSaved("saved"),
        () => setSaved("error"),
      );
    }, SAVE_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [id, useful, reasons]);

  function choose(next: boolean) {
    if (next === useful) return;
    setUseful(next);
    setReasons([]);
  }

  function toggle(reason: string) {
    setReasons((current) =>
      current.includes(reason) ? current.filter((r) => r !== reason) : [...current, reason],
    );
  }

  const toggleClass = (on: boolean) =>
    cn(
      "h-10 flex-1 rounded-sm border text-sm font-semibold transition-colors",
      focusRing,
      on ? "border-ink bg-ink text-white" : "border-line bg-white text-ink hover:bg-surface",
    );

  return (
    <section
      aria-labelledby="rating-title"
      className="flex w-full flex-col gap-3 rounded-2xl border border-line bg-white p-4 text-left"
    >
      <h2 id="rating-title" className="text-sm font-semibold text-ink">
        Was this lesson useful?
      </h2>
      <div className="flex gap-2">
        <button
          type="button"
          aria-pressed={useful === true}
          onClick={() => choose(true)}
          className={toggleClass(useful === true)}
        >
          Yes
        </button>
        <button
          type="button"
          aria-pressed={useful === false}
          onClick={() => choose(false)}
          className={toggleClass(useful === false)}
        >
          Not really
        </button>
      </div>
      {useful !== null && (
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Why? (optional)">
          {REASONS[useful ? "yes" : "no"].map((reason) => {
            const on = reasons.includes(reason.value);
            return (
              <button
                key={reason.value}
                type="button"
                aria-pressed={on}
                onClick={() => toggle(reason.value)}
                className={cn(
                  "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                  focusRing,
                  on
                    ? "border-brand/40 bg-brand-soft text-brand"
                    : "border-line bg-white text-muted hover:bg-surface hover:text-ink",
                )}
              >
                {reason.label}
              </button>
            );
          })}
        </div>
      )}
      <p role="status" className="min-h-4 text-caption text-muted">
        {saved === "saved" && "Thank you. Your feedback will shape future lessons."}
        {saved === "error" && (
          <span className="text-danger">We couldn&apos;t save that. Check your connection.</span>
        )}
      </p>
    </section>
  );
}
