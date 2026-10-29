import { ApiError, apiFetch } from "@sgjio/ui";
import { useCallback, useEffect, useState } from "react";

/** One lesson found by search (SCRUM-85), as its latest published version reads. */
export type SearchResult = {
  lesson_id: string;
  title: string;
  topic_id: string;
  topic_name: string;
  completed: boolean;
  /** Card text around the first match, or null when only the title matched. */
  snippet: string | null;
};

type State =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; results: SearchResult[] }
  | { status: "error"; message: string };

/** The server refuses anything shorter (api/app/routers/progress.py). */
export const MIN_QUERY_LENGTH = 2;
const DEBOUNCE_MS = 250;

/** The query as the server compares it: trimmed, with runs of spaces as one. */
export function normaliseQuery(query: string): string {
  return query.trim().replace(/\s+/g, " ");
}

/**
 * Searches published lessons as the user types (SCRUM-85). Waits for a short pause in typing
 * before asking, and cancels the previous request when the query changes, so an older,
 * slower answer can never replace a newer one. Idle while the query is too short to send.
 */
export function useLessonSearch(rawQuery: string) {
  const query = normaliseQuery(rawQuery);
  const searchable = query.length >= MIN_QUERY_LENGTH;
  // Bumped by "Try again", so the same query is asked again.
  const [attempt, setAttempt] = useState(0);
  // The last answer, kept with the request it answers. Until the current request's answer
  // arrives, the search reads as loading.
  const key = `${attempt}:${query}`;
  const [answer, setAnswer] = useState<{ key: string; state: State } | null>(null);

  useEffect(() => {
    if (!searchable) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      apiFetch<SearchResult[]>(`/api/search?q=${encodeURIComponent(query)}`, {
        signal: controller.signal,
      })
        .then((results) => setAnswer({ key, state: { status: "ready", results } }))
        .catch((error: unknown) => {
          if (error instanceof DOMException && error.name === "AbortError") return;
          const message =
            error instanceof ApiError ? error.message : "We couldn't search just now.";
          setAnswer({ key, state: { status: "error", message } });
        });
    }, DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [key, query, searchable]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  const state: State = !searchable
    ? { status: "idle" }
    : answer?.key === key
      ? answer.state
      : { status: "loading" };

  return { query, searchable, state, retry };
}
