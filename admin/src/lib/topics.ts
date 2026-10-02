import { ApiError, apiFetch, useAuth } from "@sgjio/ui";
import { useCallback, useEffect, useState } from "react";

/** A topic as the admin API returns it. Counts cover lessons of every status. */
export type Topic = {
  id: string;
  name: string;
  /** null while the topic is active; the time it was archived otherwise. */
  archived_at: string | null;
  lesson_count: number;
  published_count: number;
};

const BASE = "/api/admin/topics";

export const TOPIC_NAME_MAX_LENGTH = 80;

/**
 * Checks a topic name before it is sent, so the reader gets a plain message instead of the
 * framework's validation text. Mirrors TopicName in api/app/schemas.py (trimmed, 1 to 80
 * characters); the server still has the last word. Returns null when the name is fine.
 */
export function validateTopicName(name: string): string | null {
  const trimmed = name.trim();
  if (!trimmed) return "Enter a topic name.";
  if (trimmed.length > TOPIC_NAME_MAX_LENGTH) {
    return `Topic names can be up to ${TOPIC_NAME_MAX_LENGTH} characters.`;
  }
  return null;
}

/** "3 lessons (2 published)", "1 lesson (none published)" or "No lessons". */
export function lessonSummary({ lesson_count, published_count }: Topic): string {
  if (lesson_count === 0) return "No lessons";
  const lessons = `${lesson_count} ${lesson_count === 1 ? "lesson" : "lessons"}`;
  return `${lessons} (${published_count === 0 ? "none" : published_count} published)`;
}

export const createTopic = (name: string) =>
  apiFetch<Topic>(BASE, { method: "POST", body: { name } });

export const renameTopic = (id: string, name: string) =>
  apiFetch<Topic>(`${BASE}/${id}`, { method: "PATCH", body: { name } });

export const archiveTopic = (id: string) =>
  apiFetch<Topic>(`${BASE}/${id}/archive`, { method: "POST" });

export const restoreTopic = (id: string) =>
  apiFetch<Topic>(`${BASE}/${id}/restore`, { method: "POST" });

export const deleteTopic = (id: string) => apiFetch<void>(`${BASE}/${id}`, { method: "DELETE" });

type State =
  | { status: "loading" }
  | { status: "ready"; topics: Topic[] }
  | { status: "error"; message: string };

/**
 * Loads every topic, archived ones included, and runs changes to them.
 *
 * Same shape as useProgress in the main app. `run` wraps one change (create, rename,
 * archive, ...): once it finishes, success or failure, the list is fetched again, so the
 * page never shows counts that another admin or a new lesson has already changed. If that
 * refresh itself fails the list on screen is kept rather than replaced by an error.
 *
 * A 401 means the admin session ended: `refresh` makes RequireAuth send them to sign in.
 */
export function useTopics() {
  const { refresh } = useAuth();
  const [state, setState] = useState<State>({ status: "loading" });

  // Returns the next state rather than setting it, so the caller decides whether it still
  // applies. `null` means "nothing to do": cancelled, or the session ended.
  const loadTopics = useCallback(
    async (signal?: AbortSignal): Promise<State | null> => {
      try {
        return { status: "ready", topics: await apiFetch<Topic[]>(BASE, { signal }) };
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return null;
        if (error instanceof ApiError && error.status === 401) {
          void refresh();
          return null;
        }
        return {
          status: "error",
          message:
            error instanceof ApiError
              ? error.message
              : "We couldn't load the topics. Please try again.",
        };
      }
    },
    [refresh],
  );

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    void loadTopics(controller.signal).then((next) => {
      if (active && next) setState(next);
    });
    return () => {
      active = false;
      controller.abort();
    };
  }, [loadTopics]);

  /** Retry after the first load failed. */
  const reload = useCallback(() => {
    setState({ status: "loading" });
    void loadTopics().then((next) => {
      if (next) setState(next);
    });
  }, [loadTopics]);

  const run = useCallback(
    async <T>(change: () => Promise<T>): Promise<T> => {
      try {
        return await change();
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) void refresh();
        throw error;
      } finally {
        const next = await loadTopics();
        if (next?.status === "ready") setState(next);
      }
    },
    [loadTopics, refresh],
  );

  return { state, reload, run };
}
