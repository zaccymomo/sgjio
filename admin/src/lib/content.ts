import { ApiError, apiFetch, useAuth } from "@sgjio/ui";
import { useCallback, useEffect, useRef, useState } from "react";

/** A topic as /api/admin/topics returns it. Counts cover lessons of every status. */
export type Topic = {
  id: string;
  name: string;
  /** Shown under the name on the topic's page in the main app. Empty when it has none. */
  description: string;
  archived_at: string | null;
  position: number;
  lesson_count: number;
  published_count: number;
};

export type LessonStatus = "draft" | "published" | "withdrawn";

/** The three statuses SCRUM-66 lists, as the admin portal shows them. */
export const STATUS_LABELS: Record<LessonStatus, string> = {
  draft: "Draft",
  published: "Published",
  withdrawn: "Withdrawn",
};

/** A lesson as /api/admin/lessons returns it: no cards, just what the list shows. */
export type LessonSummary = {
  id: string;
  title: string;
  summary: string;
  topic_id: string | null;
  status: LessonStatus;
  updated_at: string;
  position: number;
  /** Never published. Only these can be deleted. */
  deletable: boolean;
  /** The draft differs from what users see: there is something to publish. */
  has_unpublished_changes: boolean;
  /** The latest published version, or null if never published. */
  version: number | null;
  cards: number;
  questions: number;
  /** The first image in the deck, served at /api/media/{id}. */
  cover_asset_id: string | null;
  /** Problems learners reported that nobody has dealt with yet (SCRUM-83 AC4). */
  open_reports: number;
};

export type Content = { topics: Topic[]; lessons: LessonSummary[] };

const TOPICS = "/api/admin/topics";

/** What the New topic and Edit topic dialog saves. */
export type TopicFields = { name: string; description: string };
const LESSONS = "/api/admin/lessons";

export const topicApi = {
  list: (signal?: AbortSignal) => apiFetch<Topic[]>(TOPICS, { signal }),
  create: (fields: TopicFields) => apiFetch<Topic>(TOPICS, { method: "POST", body: fields }),
  update: (id: string, fields: TopicFields) =>
    apiFetch<Topic>(`${TOPICS}/${id}`, { method: "PATCH", body: fields }),
  archive: (id: string) => apiFetch<Topic>(`${TOPICS}/${id}/archive`, { method: "POST" }),
  restore: (id: string) => apiFetch<Topic>(`${TOPICS}/${id}/restore`, { method: "POST" }),
  remove: (id: string) => apiFetch<void>(`${TOPICS}/${id}`, { method: "DELETE" }),
};

/** The server refuses a reorder of a list that has changed since it was loaded. */
function isOutOfDate(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.code === "order_out_of_date" || error.code === "topic_not_found")
  );
}

const LIST_CHANGED =
  "The list changed in another tab or by another administrator. We've loaded the latest " +
  "order. Please try again.";

type State =
  | { status: "loading" }
  | { status: "ready"; content: Content }
  | { status: "error"; message: string };

export type Notice = { tone: "success" | "error" | "info"; message: string };

/**
 * Loads every topic and every lesson for the admin content page (SCRUM-66).
 *
 * Same shape as useProgress in the main app: fetches on mount, refreshes quietly when the
 * tab regains focus, and `retry` is what the error state calls. On top of that:
 *
 * - a 401 (the admin session expired) re-checks the session, so RequireAuth sends the
 *   administrator to sign in and back here afterwards
 * - `run` performs a change and then reloads both lists, since a topic change alters the
 *   counts and a lesson change alters the topics
 * - the reorder functions move things on screen at once, then save. If the save fails they
 *   put the old order back; if the list was out of date they load the latest one instead.
 *   While a save runs, `saving` is true and the page disables reordering.
 *
 * `initialNotice` is a message another page sent along, e.g. "deleted" from the editor.
 */
export function useContent(initialNotice: Notice | null = null) {
  const { refresh: recheckSession } = useAuth();
  const [state, setState] = useState<State>({ status: "loading" });
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(initialNotice);
  // A drag or a save in progress. A quiet refresh then would move rows under the pointer.
  const busy = useRef(false);

  const handleSessionExpiry = useCallback(
    (error: unknown): boolean => {
      if (error instanceof ApiError && error.status === 401) {
        void recheckSession();
        return true;
      }
      return false;
    },
    [recheckSession],
  );

  // Returns the next state rather than setting it, so the caller decides whether it still
  // applies. `null` means there is nothing to show: the request was cancelled, or the
  // session expired and the page is about to be replaced by sign-in.
  const load = useCallback(
    async (signal?: AbortSignal): Promise<State | null> => {
      try {
        const [topics, lessons] = await Promise.all([
          apiFetch<Topic[]>(TOPICS, { signal }),
          apiFetch<LessonSummary[]>(LESSONS, { signal }),
        ]);
        return { status: "ready", content: { topics, lessons } };
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return null;
        if (handleSessionExpiry(error)) return null;
        return {
          status: "error",
          message:
            error instanceof ApiError
              ? error.message
              : "We couldn't load topics and lessons. Please try again.",
        };
      }
    },
    [handleSessionExpiry],
  );

  // A failed quiet refresh keeps what is on screen and says so, rather than replacing a
  // working page with an error.
  const applyQuietly = useCallback((next: State | null) => {
    if (!next) return;
    if (next.status === "error") {
      setState((current) => (current.status === "ready" ? current : next));
      setNotice({ tone: "error", message: `We couldn't refresh the list. ${next.message}` });
    } else {
      setState(next);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    void load(controller.signal).then((next) => {
      if (active && next) setState(next);
    });

    const refreshOnReturn = () => {
      if (document.visibilityState !== "visible" || busy.current) return;
      void load(controller.signal).then((next) => {
        if (active && !busy.current) applyQuietly(next);
      });
    };
    document.addEventListener("visibilitychange", refreshOnReturn);

    return () => {
      active = false;
      controller.abort();
      document.removeEventListener("visibilitychange", refreshOnReturn);
    };
  }, [load, applyQuietly]);

  /** Retry after a failed load. Shows the spinner again, since there is nothing to keep. */
  const retry = useCallback(() => {
    setState({ status: "loading" });
    void load().then((next) => {
      if (next) setState(next);
    });
  }, [load]);

  /** Load the latest lists without a spinner. */
  const refresh = useCallback(async () => applyQuietly(await load()), [load, applyQuietly]);

  /**
   * Perform a change, then reload both lists, whether it worked or not: a refusal such as
   * "topic not empty" usually means the page was out of date. Resolves once the lists are
   * fresh. Errors are re-thrown so the dialog that asked can show them.
   */
  const run = useCallback(
    async <T>(action: () => Promise<T>): Promise<T> => {
      try {
        return await action();
      } catch (error) {
        handleSessionExpiry(error);
        throw error;
      } finally {
        await refresh();
      }
    },
    [handleSessionExpiry, refresh],
  );

  const current = state.status === "ready" ? state.content : null;

  const save = useCallback(
    async (optimistic: Content, request: () => Promise<Partial<Content>>) => {
      if (!current) return;
      const before = current;
      setState({ status: "ready", content: optimistic });
      setSaving(true);
      busy.current = true;
      try {
        const saved = await request();
        setState((now) =>
          now.status === "ready" ? { status: "ready", content: { ...now.content, ...saved } } : now,
        );
        setNotice({ tone: "success", message: "Order saved." });
      } catch (error) {
        if (handleSessionExpiry(error)) return;
        if (isOutOfDate(error)) {
          await refresh();
          setNotice({ tone: "info", message: LIST_CHANGED });
        } else {
          setState({ status: "ready", content: before });
          setNotice({
            tone: "error",
            message:
              error instanceof ApiError
                ? `The new order wasn't saved. ${error.message}`
                : "The new order wasn't saved. Please try again.",
          });
        }
      } finally {
        busy.current = false;
        setSaving(false);
      }
    },
    [current, handleSessionExpiry, refresh],
  );

  /** Every active topic in the new order, and in the order the page showed. */
  const reorderTopics = useCallback(
    (ids: string[], previousIds: string[]) => {
      if (!current) return;
      const byId = new Map(current.topics.map((topic) => [topic.id, topic]));
      const moved = ids.flatMap((id, position) => {
        const topic = byId.get(id);
        return topic ? [{ ...topic, position }] : [];
      });
      const others = current.topics.filter((topic) => !ids.includes(topic.id));
      void save({ ...current, topics: [...moved, ...others] }, async () => ({
        topics: await apiFetch<Topic[]>(`${TOPICS}/order`, {
          method: "PUT",
          body: { ids, previous_ids: previousIds },
        }),
      }));
    },
    [current, save],
  );

  /**
   * Every lesson in that topic (or with no topic, `topicId` null), in the new order and in
   * the order the page showed.
   */
  const reorderLessons = useCallback(
    (topicId: string | null, ids: string[], previousIds: string[]) => {
      if (!current) return;
      const position = new Map(ids.map((id, index) => [id, index]));
      const lessons = current.lessons.map((lesson) =>
        position.has(lesson.id) ? { ...lesson, position: position.get(lesson.id)! } : lesson,
      );
      void save({ ...current, lessons }, async () => ({
        lessons: await apiFetch<LessonSummary[]>(`${LESSONS}/order`, {
          method: "PUT",
          body: { topic_id: topicId, ids, previous_ids: previousIds },
        }),
      }));
    },
    [current, save],
  );

  /** Tell the hook a drag has started or ended, so a quiet refresh waits for it. */
  const setDragging = useCallback((dragging: boolean) => {
    busy.current = dragging;
  }, []);

  return {
    state,
    saving,
    notice,
    setNotice,
    retry,
    refresh,
    run,
    reorderTopics,
    reorderLessons,
    setDragging,
    handleSessionExpiry,
  };
}
