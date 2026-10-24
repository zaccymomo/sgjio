import { ApiError, apiFetch } from "@sgjio/ui";
import { useCallback, useEffect, useState } from "react";

/** A question answered wrongly, as its lesson reads now (SCRUM-44). */
export type Mistake = {
  lesson_id: string;
  lesson_title: string;
  topic_name: string;
  question_id: string;
  /** The card's Markdown, with its {{blank}} if it has one. */
  text: string;
  chosen: string;
  correct: string;
  explanation: string;
  /** Why the chosen option isn't the norm, empty when the lesson doesn't say. */
  why_not: string;
  answered_at: string;
};

type State =
  | { status: "loading" }
  | { status: "ready"; mistakes: Mistake[] }
  | { status: "error"; message: string };

/** Loads the signed-in user's mistakes, with a `reload` for the error state's retry. */
export function useReview() {
  const [state, setState] = useState<State>({ status: "loading" });

  const load = useCallback(async (signal?: AbortSignal): Promise<State | null> => {
    try {
      const { mistakes } = await apiFetch<{ mistakes: Mistake[] }>("/api/review", { signal });
      return { status: "ready", mistakes };
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return null;
      return {
        status: "error",
        message:
          error instanceof ApiError
            ? error.message
            : "We couldn't load your mistakes. Please try again.",
      };
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal).then((next) => next && setState(next));
    return () => controller.abort();
  }, [load]);

  const reload = useCallback(async () => {
    setState({ status: "loading" });
    const next = await load();
    if (next) setState(next);
  }, [load]);

  return { state, reload };
}
