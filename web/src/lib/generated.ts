import { ApiError, apiFetch } from "@sgjio/ui";
import { useCallback, useEffect, useState } from "react";

/**
 * AI-generated lessons (docs/ai-lessons-plan.md): the shapes of Learning's API, as
 * docs/ai-lessons-api.md "Learning" describes them, and the labels the screens share.
 */

export type Focus = "new" | "mistakes";
export type Difficulty = "easier" | "right" | "harder";
export type Length = "short" | "usual";
export type GeneratedStatusName =
  "requested" | "writing" | "checking" | "ready" | "failed" | "cancelled";

/** GET /api/generate/options */
export type GenerateOptions = {
  daily_limit: number;
  left_today: number;
  has_generated: boolean;
  mistakes_total: number;
  pick_for_me: { new: string | null; mistakes: string | null };
  topics: { id: string; name: string; mistakes: number; level: number }[];
};

/** The body of POST /api/generate. `topic_id` null means Pick for me. */
export type GenerateChoices = {
  topic_id: string | null;
  focus: Focus;
  ask: string | null;
  difficulty: Difficulty;
  length: Length;
};

/** GET /api/generate/{id}: one request, as the Generating and Ready screens need it. */
export type GeneratedStatus = {
  id: string;
  status: GeneratedStatusName;
  topic: { id: string; name: string };
  focus: Focus;
  difficulty: Difficulty;
  length: Length;
  level: number;
  ask: string | null;
  covers: { lesson_id: string; lesson_title: string; correct: string }[];
  lesson: null | {
    title: string;
    summary: string;
    learning_points: string[];
    cards: number;
    questions: number;
    reading_seconds: number;
  };
  failure: null | {
    code: "off_topic" | "invalid_output" | "unsafe" | "provider" | "timeout";
    message: string;
  };
  created_at: string;
  left_today: number;
};

/** One row of GET /api/generated (failed and cancelled ones are left out). */
export type GeneratedListItem = {
  id: string;
  status: "requested" | "writing" | "checking" | "ready";
  title: string | null;
  topic: { id: string; name: string };
  created_at: string;
  best: { correct: number; scored: number } | null;
};

export const WAITING: GeneratedStatusName[] = ["requested", "writing", "checking"];

export const FOCUS_LABELS: Record<Focus, string> = {
  new: "Something new",
  mistakes: "My mistakes",
};

export const DIFFICULTY_LABELS: Record<Difficulty, string> = {
  easier: "Easier",
  right: "At my level",
  harder: "Harder",
};

export const LENGTH_LABELS: Record<Length, string> = {
  short: "Short (about 1 min)",
  usual: "Standard (about 2 min)",
};

export const LENGTH_TIME: Record<Length, string> = {
  short: "About 1 min",
  usual: "About 2 min",
};

/** The choices a request was made with, to make it again or change them. */
export function choicesOf(status: GeneratedStatus): GenerateChoices {
  return {
    topic_id: status.topic.id,
    focus: status.focus,
    ask: status.ask,
    difficulty: status.difficulty,
    length: status.length,
  };
}

/** POST /api/generate: starts a request and returns it (202). */
export function startGeneration(choices: GenerateChoices): Promise<GeneratedStatus> {
  return apiFetch<GeneratedStatus>("/api/generate", { method: "POST", body: choices });
}

/** True for the 429 that says today's lessons are used up. */
export function isDailyLimit(error: unknown): boolean {
  return error instanceof ApiError && error.code === "daily_limit_reached";
}

export function dailyLimitMessage(limit: number): string {
  return `You have reached today's limit of ${limit} generated lessons. You can generate more tomorrow.`;
}

/** The server's message, or a fallback when the server couldn't be reached. */
export function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError && error.status !== 0 ? error.message : fallback;
}

/** "Today", "Yesterday" or "7 Nov", in the viewer's time zone. */
export function dayLabel(iso: string): string {
  const date = new Date(iso);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (date.toDateString() === today.toDateString()) return "Today";
  if (date.toDateString() === yesterday.toDateString()) return "Yesterday";
  return date.toLocaleDateString("en-SG", { day: "numeric", month: "short" });
}

export function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

type OptionsState =
  | { status: "loading" }
  | { status: "ready"; options: GenerateOptions }
  | { status: "error"; message: string };

/** Loads GET /api/generate/options, with a `reload` for the error state's retry. */
export function useGenerateOptions() {
  const [state, setState] = useState<OptionsState>({ status: "loading" });

  const load = useCallback(async (signal?: AbortSignal): Promise<OptionsState | null> => {
    try {
      const options = await apiFetch<GenerateOptions>("/api/generate/options", { signal });
      return { status: "ready", options };
    } catch (error) {
      if (signal?.aborted) return null;
      return {
        status: "error",
        message: errorMessage(error, "We couldn't load this page. Check your connection."),
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
