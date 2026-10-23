import { apiFetch } from "@sgjio/ui";
import type { Assets, LessonDoc } from "@sgjio/ui/lesson";

import type { LessonStatus } from "./content";

/**
 * How learners do on one version of a lesson (SCRUM-84), as GET
 * /api/admin/lessons/{id}/insights returns it. Mirrors LessonInsightsOut in
 * api/app/schemas.py. Shares are fractions from 0 to 1. A figure is null where fewer than
 * `min_learners` learners are behind it, and nothing here names a learner.
 */
export type Learners = "all" | "newcomer" | "singaporean";

export type InsightsQuestion = {
  id: string;
  /** Its place among the questions, and its card's place in the deck, from 1. */
  number: number;
  card_number: number;
  /** The card's Markdown, with its {{blank}}. */
  text: string;
  right_first_time: number;
  previous_right_first_time: number | null;
  /** Of those wrong first time who took it again, the share right on a later run. */
  fixed_on_retake: number | null;
  newcomers: number | null;
  singaporeans: number | null;
  options: { id: string; text: string; correct: boolean; chosen: number }[];
};

export type TrendSeries = {
  version: number;
  /** Learners finishing it for the first time, each week. */
  finished: (number | null)[];
  /** Running figures, null until enough learners have finished the version. */
  average_best: (number | null)[];
  right_first_time: (number | null)[];
  finish_rate: (number | null)[];
};

export type LessonInsights = {
  id: string;
  title: string;
  status: LessonStatus;
  topic_name: string | null;
  /** Newest first. */
  versions: { number: number; published_at: string }[];
  version: number | null;
  learners: Learners;
  min_learners: number;
  /** Whether enough learners have finished this version; if not, every figure is null. */
  enough: boolean;
  summary: {
    learners: number;
    share_of_learners: number;
    average_best: number;
    right_first_time: number | null;
    finish_rate: number;
    previous: { number: number; average_best: number; right_first_time: number | null } | null;
  } | null;
  questions: InsightsQuestion[] | null;
  /** Runs that answered each question (question: 1, 2...), then reached the end (null). */
  funnel: { question: number | null; runs: number }[] | null;
  /** How many learners got 0, 1, 2... questions right on their first run. */
  scores: { correct: number; learners: number }[] | null;
  /** Mondays (YYYY-MM-DD), and each version's figures for each of them. */
  trend: { weeks: string[]; series: TrendSeries[] };
  /** The version's deck and files, to preview exactly what learners saw. */
  doc: LessonDoc | null;
  assets: Assets;
  reading_seconds: number;
};

export const insightsApi = {
  get: (id: string, query: { version?: number; learners: Learners }, signal?: AbortSignal) => {
    const params = new URLSearchParams({ learners: query.learners });
    if (query.version) params.set("version", String(query.version));
    return apiFetch<LessonInsights>(`/api/admin/lessons/${id}/insights?${params}`, { signal });
  },
};

/** 0.416 -> "42%". */
export function percent(share: number): string {
  return `${Math.round(share * 100)}%`;
}
