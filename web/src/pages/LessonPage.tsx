import { ApiError, apiFetch, Button, ErrorState, FullPageSpinner } from "@sgjio/ui";
import {
  LessonDeck,
  type Assets,
  type CheckResult,
  type DeckSummary,
  type LearnerCard,
} from "@sgjio/ui/lesson";
import { ChevronLeft, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

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

type Score = { correct: number; scored: number };
type AttemptResult = {
  attempt_id: string;
  score: Score;
  best: Score;
  first_completion: boolean;
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
 */
export function LessonPage() {
  const { lessonId = "" } = useParams();
  const navigate = useNavigate();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [save, setSave] = useState<Save>({ status: "idle" });
  const attempt = useRef<Promise<string> | null>(null);
  const finished = useRef<string | null>(null);

  const fetchLesson = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const lesson = await apiFetch<LearnerLesson>(`/api/lessons/${lessonId}`, { signal });
        return { status: "ready", lesson } as const;
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return null;
        const missing = error instanceof ApiError && error.status === 404;
        return {
          status: "error",
          message: missing
            ? "This lesson isn't available any more. It may have been removed."
            : message(error, "We couldn't load this lesson. Check your connection and try again."),
          retry: !missing,
        } as const;
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
    navigate(`/topics/${lesson.topic.id}`, { state: { topicName: lesson.topic.name } });
  }, [lesson, navigate]);

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
    <div className="h-dvh">
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
      />
    </div>
  );
}
