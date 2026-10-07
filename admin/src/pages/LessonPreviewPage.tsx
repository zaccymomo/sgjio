import { ApiError, Button, ErrorState, FullPageSpinner, useAuth } from "@sgjio/ui";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { LessonPreview } from "../components/LessonPreview";
import { topicApi, type Topic } from "../lib/content";
import { lessonApi, type Lesson } from "../lib/lessons";

type Load =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "not-found" }
  | { status: "ready"; lesson: Lesson; topics: Topic[] };

/**
 * A lesson's saved draft, previewed as learners will see it (SCRUM-65), at
 * /lessons/:id/preview. The editor opens the same preview over itself for unsaved edits.
 */
export function LessonPreviewPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { refresh: recheckSession } = useAuth();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([lessonApi.get(id, controller.signal), topicApi.list(controller.signal)])
      .then(([lesson, topics]) => setLoad({ status: "ready", lesson, topics }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        if (error instanceof ApiError && error.status === 401) return void recheckSession();
        if (
          error instanceof ApiError &&
          (error.code === "lesson_not_found" || error.code === "validation_error")
        ) {
          return setLoad({ status: "not-found" });
        }
        setLoad({ status: "error", message: "We couldn't load this lesson. Please try again." });
      });
    return () => controller.abort();
  }, [id, attempt, recheckSession]);

  const close = () => navigate(`/lessons/${id}`);

  if (load.status === "loading") return <FullPageSpinner />;
  if (load.status !== "ready") {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-surface p-6">
        {load.status === "error" ? (
          <ErrorState
            message={load.message}
            onRetry={() => {
              setLoad({ status: "loading" });
              setAttempt((n) => n + 1);
            }}
          />
        ) : (
          <div className="flex flex-col items-center gap-3 text-center">
            <p className="text-base font-bold text-ink">That lesson no longer exists</p>
            <Button variant="secondary" onClick={() => navigate("/")}>
              Go to all content
            </Button>
          </div>
        )}
      </div>
    );
  }

  const { lesson, topics } = load;
  return (
    <LessonPreview
      lesson={{
        title: lesson.title,
        summary: lesson.summary,
        topicName: topics.find((topic) => topic.id === lesson.topic_id)?.name ?? null,
        readingSeconds: lesson.stats.reading_seconds,
      }}
      doc={lesson.doc}
      assets={lesson.assets}
      onClose={close}
    />
  );
}
