import { ApiError, apiFetch } from "@sgjio/ui";
import { useCallback, useEffect, useState } from "react";

/** One progress circle. The two figures are defined in SCRUM-16 AC7. */
export type TopicProgress = {
  id: string;
  name: string;
  completed: number;
  available: number;
};

export type Progress = {
  topics: TopicProgress[];
  completed: number;
  available: number;
};

type State =
  | { status: "loading" }
  | { status: "ready"; progress: Progress }
  | { status: "error"; message: string };

/**
 * Loads the signed-in user's progress.
 *
 * Fetches on mount, so returning to the landing page after answering a quiz shows the new
 * figures without a page reload (SCRUM-43 AC8), and again when the tab regains focus, which
 * covers answering a quiz in another tab. `reload` is what the error state's retry calls
 * (AC10).
 */
export function useProgress() {
  const [state, setState] = useState<State>({ status: "loading" });

  // Returns the next state rather than setting it, so the caller decides whether it still
  // applies. Same shape as loadCurrentUser in AuthProvider. `null` means "nothing to do":
  // the request was cancelled because the page went away.
  const loadProgress = useCallback(async (signal?: AbortSignal): Promise<State | null> => {
    try {
      const progress = await apiFetch<Progress>("/api/progress", { signal });
      return { status: "ready", progress };
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return null;
      return {
        status: "error",
        message:
          error instanceof ApiError
            ? error.message
            : "We couldn't load your progress. Please try again.",
      };
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const apply = (next: State | null) => {
      if (active && next) setState(next);
    };

    void loadProgress(controller.signal).then(apply);

    // Refresh quietly on return: the figures already on screen stay until the new ones
    // arrive, rather than flashing a spinner every time someone switches back to the tab.
    const refreshOnReturn = () => {
      if (document.visibilityState === "visible") void loadProgress(controller.signal).then(apply);
    };
    document.addEventListener("visibilitychange", refreshOnReturn);

    return () => {
      active = false;
      controller.abort();
      document.removeEventListener("visibilitychange", refreshOnReturn);
    };
  }, [loadProgress]);

  /** Retry after a failure. Shows the spinner again, since there is nothing worth keeping. */
  const reload = useCallback(() => {
    setState({ status: "loading" });
    void loadProgress().then((next) => {
      if (next) setState(next);
    });
  }, [loadProgress]);

  return { state, reload };
}
