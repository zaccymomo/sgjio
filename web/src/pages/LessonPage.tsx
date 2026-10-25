import { ApiError, apiFetch, Button, ErrorState, FullPageSpinner } from "@sgjio/ui";
import {
  LessonDeck,
  type Assets,
  type CheckResult,
  type DeckSummary,
  type LearnerCard,
} from "@sgjio/ui/lesson";
import { Check, ChevronLeft, Flag, PartyPopper, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { ReportProblemDialog } from "../components/ReportProblemDialog";

/** A lesson as GET /api/lessons/{id} returns it: never says which option is right. */
type LearnerLesson = {
  id: string;
  version: number;
  title: string;
  summary: string;
  topic: { id: string; name: string };
  reading_seconds: number;
  cards: LearnerCard[];
  assets: Assets;
};

/** How long a lesson may take to load before the page says so and offers a retry. */
const LOAD_TIMEOUT_MS = 15_000;

type Score = { correct: number; scored: number };
type AttemptResult = {
  attempt_id: string;
  score: Score;
  best: Score;
  first_completion: boolean;
  /** This completed the last lesson the topic needed (SCRUM-55 AC1). */
  topic_completed: boolean;
};

type Load =
  | { status: "loading" }
  | { status: "ready"; lesson: LearnerLesson }
  | { status: "error"; message: string; retry: boolean };

type Save =
  | { status: "idle" }
  | { status: "saving" }
  | { status: "saved"; result: AttemptResult }
  | { status: "error"; message: string };

function message(error: unknown, fallback: string): string {
  return error instanceof ApiError && error.status !== 0 ? error.message : fallback;
}

/**
 * Taking a lesson (SCRUM-15): the shared deck, with answers checked and recorded on the
 * server (SCRUM-16).
 *
 * The first answer starts an attempt at the version shown, and reaching the end card
 * finishes it, which is what completes the lesson. Leaving earlier records nothing, and
 * the lesson opens from its cover next time (AC4). Closing, or "Back to …" at the end,
 * returns to the lesson's topic (AC13).
 *
 * Every card has "Report a problem" in its top bar (SCRUM-82). The report form opens over
 * the deck, so sending it leaves the learner on the same card.
 */
export function LessonPage() {
  const { lessonId = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [save, setSave] = useState<Save>({ status: "idle" });
  // The card being reported, and whether the last report was just sent (SCRUM-82).
  const [reporting, setReporting] = useState<{ id: string; number: number } | null>(null);
  const [reportSent, setReportSent] = useState(false);
  const attempt = useRef<Promise<string> | null>(null);
  const finished = useRef<string | null>(null);

  const fetchLesson = useCallback(
    async (signal?: AbortSignal) => {
      // A load that hangs is reported like a failed one, so nobody waits on a spinner
      // forever (AC3).
      const timeout = new AbortController();
      const timer = window.setTimeout(() => timeout.abort(), LOAD_TIMEOUT_MS);
      signal?.addEventListener("abort", () => timeout.abort());
      try {
        const lesson = await apiFetch<LearnerLesson>(`/api/lessons/${lessonId}`, {
          signal: timeout.signal,
        });
        return { status: "ready", lesson } as const;
      } catch (error) {
        if (signal?.aborted) return null;
        const missing = error instanceof ApiError && error.status === 404;
        return {
          status: "error",
          message: missing
            ? "This lesson isn't available any more. It may have been removed."
            : message(error, "We couldn't load this lesson. Check your connection and try again."),
          retry: !missing,
        } as const;
      } finally {
        window.clearTimeout(timer);
      }
    },
    [lessonId],
  );

  useEffect(() => {
    const controller = new AbortController();
    void fetchLesson(controller.signal).then((next) => next && setLoad(next));
    return () => controller.abort();
  }, [fetchLesson]);

  function reload() {
    attempt.current = null;
    finished.current = null;
    setSave({ status: "idle" });
    setLoad({ status: "loading" });
    void fetchLesson().then((next) => next && setLoad(next));
  }

  const lesson = load.status === "ready" ? load.lesson : null;

  useEffect(() => {
    if (!reportSent) return;
    const timer = window.setTimeout(() => setReportSent(false), 5000);
    return () => window.clearTimeout(timer);
  }, [reportSent]);

  /** The attempt this run of the deck records to, started by its first answer. */
  const ensureAttempt = useCallback(() => {
    if (!lesson) return Promise.reject(new Error("No lesson loaded."));
    attempt.current ??= apiFetch<{ id: string }>(`/api/lessons/${lesson.id}/attempts`, {
      method: "POST",
      body: { version: lesson.version },
    }).then(
      ({ id }) => id,
      (error: unknown) => {
        attempt.current = null;
        if (error instanceof ApiError && error.code === "lesson_updated") {
          setLoad({ status: "error", message: error.message, retry: true });
        }
        throw error;
      },
    );
    return attempt.current;
  }, [lesson]);

  const check = useCallback(
    async (questionId: string, optionId: string) => {
      const id = await ensureAttempt();
      return apiFetch<CheckResult>(`/api/attempts/${id}/answers`, {
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
      const id = await attempt.current;
      const result = await apiFetch<AttemptResult>(`/api/attempts/${id}/finish`, {
        method: "POST",
      });
      finished.current = id;
      setSave({ status: "saved", result });
    } catch (error) {
      setSave({
        status: "error",
        message: message(error, "We couldn't save your progress. Check your connection."),
      });
    }
  }, []);

  const onFinish = useCallback(() => {
    // Coming back to the end card after a save changes nothing; the server would agree.
    void attempt.current?.then((id) => {
      if (finished.current !== id) void finish();
    });
  }, [finish]);

  const backToTopic = useCallback(() => {
    if (!lesson) return navigate("/");
    // Opened from the topic page: step back to it, so the history stays home -> topic and
    // the browser's back button then leads home (SCRUM-53 AC3, AC4). Opened any other way,
    // for example from a link, the topic replaces the lesson instead.
    if ((location.state as { fromTopic?: boolean } | null)?.fromTopic) return navigate(-1);
    navigate(`/topics/${lesson.topic.id}`, { replace: true });
  }, [lesson, location.state, navigate]);

  if (load.status === "loading") return <FullPageSpinner />;
  if (load.status === "error") {
    return (
      <div className="flex min-h-dvh flex-col bg-white px-4 py-6">
        <Link
          to="/"
          className="inline-flex w-fit items-center gap-1 rounded-sm text-sm font-medium text-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
        >
          <ChevronLeft className="size-4" aria-hidden />
          Your progress
        </Link>
        <ErrorState message={load.message} onRetry={load.retry ? reload : undefined} />
      </div>
    );
  }

  const { lesson: ready } = load;

  function renderEnd(_summary: DeckSummary, restart: () => void) {
    return (
      <>
        {/* SCRUM-55 AC1: only the finish that completes the topic sets this, so a retake
            in a finished topic doesn't repeat it. */}
        {save.status === "saved" && save.result.topic_completed && (
          <div
            role="status"
            className="flex w-full items-center gap-3 rounded-2xl border border-brand/30 bg-brand-soft/60 p-4 text-left"
          >
            <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-brand text-white">
              <PartyPopper className="size-5" aria-hidden />
            </span>
            <span className="flex flex-col">
              <span className="text-base font-bold text-ink">Topic complete</span>
              <span className="text-sm text-muted">
                You&apos;ve completed every lesson in {ready.topic.name}. You can reopen any of them
                whenever you like.
              </span>
            </span>
          </div>
        )}
        <p role="status" className="min-h-5 text-center text-sm text-muted">
          {save.status === "saving" && "Saving your progress…"}
          {save.status === "saved" &&
            (save.result.first_completion
              ? "Lesson completed and saved to your progress."
              : save.result.best.scored > 0
                ? `Saved. Your best is ${save.result.best.correct} of ${save.result.best.scored}.`
                : "Saved to your progress.")}
          {save.status === "error" && <span className="text-danger">{save.message}</span>}
        </p>
        {save.status === "error" && (
          <Button variant="secondary" onClick={() => void finish()}>
            Try saving again
          </Button>
        )}
        <button
          type="button"
          onClick={backToTopic}
          className="flex h-14 w-full items-center justify-center gap-2 rounded-2xl bg-ink text-base font-bold text-white shadow-[0_3px_0_0_#000] transition-[transform,background-color] hover:bg-ink/90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand active:translate-y-[2px]"
        >
          Back to {ready.topic.name}
        </button>
        <button
          type="button"
          onClick={() => {
            attempt.current = null;
            finished.current = null;
            setSave({ status: "idle" });
            restart();
          }}
          className="flex h-12 w-full items-center justify-center gap-2 rounded-2xl text-base font-semibold text-muted hover:bg-ink/5 hover:text-ink"
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
          title: ready.title,
          summary: ready.summary,
          topicName: ready.topic.name,
          readingSeconds: ready.reading_seconds,
        }}
        cards={ready.cards}
        assets={ready.assets}
        check={check}
        onExit={backToTopic}
        onFinish={onFinish}
        renderEnd={renderEnd}
        cardActions={(card) => (
          <button
            type="button"
            onClick={() => {
              setReportSent(false);
              setReporting({ id: card.id, number: ready.cards.indexOf(card) + 1 });
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
        lessonId={ready.id}
        version={ready.version}
        cardId={reporting?.id ?? ""}
        cardNumber={reporting?.number ?? 0}
        onClose={() => setReporting(null)}
        onSent={() => {
          setReporting(null);
          setReportSent(true);
        }}
      />
      {/* AC2: a confirmation, over the card the learner carries on from. */}
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
