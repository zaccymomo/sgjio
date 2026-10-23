import { ApiError, apiFetch } from "@sgjio/ui";
import { useCallback, useEffect, useState } from "react";

/** One lesson in a topic's list (SCRUM-53). */
export type TopicLesson = {
  id: string;
  title: string;
  summary: string;
  reading_seconds: number;
  /** Scored questions only: a one-option tap is not counted. */
  questions: number;
  completed: boolean;
  /** The best result so far (SCRUM-16), null until the lesson is completed. */
  best_correct: number | null;
  best_scored: number | null;
  /** When the user last finished it (SCRUM-54), null until the lesson is completed. */
  last_attempted_at: string | null;
};

/** A topic opened from its circle. The figures match that circle (SCRUM-16 AC8). */
export type Topic = {
  id: string;
  name: string;
  /** What the topic covers, shown under its name (SCRUM-86). Empty when it has none. */
  description: string;
  completed: number;
  available: number;
  lessons: TopicLesson[];
};

type State =
  | { status: "loading" }
  | { status: "ready"; topic: Topic }
  | { status: "unavailable"; message: string }
  | { status: "error"; message: string };

/**
 * Loads one topic's lessons for the signed-in user.
 *
 * Same shape as useProgress: fetches on mount, so coming back from a lesson shows its tick,
 * and quietly again when the tab regains focus. An archived or unknown topic is
 * "unavailable" rather than an error, since retrying will not help. The caller keys the
 * page on the topic id, so moving to another topic starts from "loading" again.
 */
export function useTopic(topicId: string) {
  const [state, setState] = useState<State>({ status: "loading" });

  const loadTopic = useCallback(
    async (signal?: AbortSignal): Promise<State | null> => {
      try {
        const topic = await apiFetch<Topic>(`/api/topics/${encodeURIComponent(topicId)}`, {
          signal,
        });
        return { status: "ready", topic };
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return null;
        // A malformed id is refused by validation (422) before the topic is looked up.
        if (error instanceof ApiError && (error.status === 404 || error.status === 422)) {
          return {
            status: "unavailable",
            message: "This topic isn't available any more. It may have been removed.",
          };
        }
        return {
          status: "error",
          message:
            error instanceof ApiError
              ? error.message
              : "We couldn't load this topic. Please try again.",
        };
      }
    },
    [topicId],
  );

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const apply = (next: State | null) => {
      if (active && next) setState(next);
    };

    void loadTopic(controller.signal).then(apply);

    const refreshOnReturn = () => {
      if (document.visibilityState === "visible") void loadTopic(controller.signal).then(apply);
    };
    document.addEventListener("visibilitychange", refreshOnReturn);

    return () => {
      active = false;
      controller.abort();
      document.removeEventListener("visibilitychange", refreshOnReturn);
    };
  }, [loadTopic]);

  const reload = useCallback(() => {
    setState({ status: "loading" });
    void loadTopic().then((next) => {
      if (next) setState(next);
    });
  }, [loadTopic]);

  return { state, reload };
}
