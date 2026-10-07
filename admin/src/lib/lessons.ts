import { apiFetch } from "@sgjio/ui";
import type { Asset, Assets, Issue, LessonDoc, LessonStats } from "@sgjio/ui/lesson";

import type { LessonStatus } from "./content";

/**
 * What the editor changes (SCRUM-19, SCRUM-64): the draft's title, summary and cards, and
 * the lesson's topic. Mirrors LessonFields in api/app/schemas.py. `topic_id: null` means no
 * topic yet.
 */
export type Draft = {
  title: string;
  summary: string;
  topic_id: string | null;
  doc: LessonDoc;
};

/** One lesson as GET /api/admin/lessons/{id} returns it: the draft, with everything the
 * editor shows about it. */
export type Lesson = Draft & {
  id: string;
  key: string | null;
  status: LessonStatus;
  published_at: string | null;
  withdrawn_at: string | null;
  position: number;
  created_at: string;
  updated_at: string;
  /** Never published. Only these can be deleted. */
  deletable: boolean;
  /** The draft differs from what users see: there is something to publish. */
  has_unpublished_changes: boolean;
  /** The latest published version, or null if never published. */
  version: { number: number; published_at: string } | null;
  /** What still stops it being published (blockers), and what is worth a look (warnings). */
  issues: Issue[];
  stats: LessonStats;
  /** The images and audio its cards use, by id. */
  assets: Assets;
};

/** Same limits as the API (schemas.py and lesson_doc.py). */
export const MAX_TITLE = 200;
export const MAX_SUMMARY = 160;
export const MAX_CARD_TEXT = 1500;
export const MAX_OPTIONS = 4;
export const MAX_OPTION_TEXT = 160;
export const CARD_WORD_LIMIT = 50;

export function draftOf(lesson: Lesson): Draft {
  return {
    title: lesson.title,
    summary: lesson.summary,
    topic_id: lesson.topic_id,
    doc: lesson.doc,
  };
}

/** Whether saving `a` would change `b`. Titles and summaries are trimmed on save. */
export function sameDraft(a: Draft, b: Draft): boolean {
  return (
    a.title.trim() === b.title.trim() &&
    a.summary.trim() === b.summary.trim() &&
    a.topic_id === b.topic_id &&
    JSON.stringify(a.doc) === JSON.stringify(b.doc)
  );
}

const LESSONS = "/api/admin/lessons";

function body(draft: Draft) {
  return { ...draft, title: draft.title.trim(), summary: draft.summary.trim() };
}

/**
 * Every change sends the `updated_at` the editor last had. If the lesson has changed since,
 * in another tab or by another administrator, the server refuses with lesson_out_of_date
 * rather than overwrite that change.
 */
export const lessonApi = {
  get: (id: string, signal?: AbortSignal) => apiFetch<Lesson>(`${LESSONS}/${id}`, { signal }),
  create: (draft: Draft) => apiFetch<Lesson>(LESSONS, { method: "POST", body: body(draft) }),
  save: (lesson: Pick<Lesson, "id" | "updated_at">, draft: Draft) =>
    apiFetch<Lesson>(`${LESSONS}/${lesson.id}`, {
      method: "PATCH",
      body: { ...body(draft), updated_at: lesson.updated_at },
    }),
  change: (
    lesson: Pick<Lesson, "id" | "updated_at">,
    action: "publish" | "discard" | "withdraw" | "restore",
  ) =>
    apiFetch<Lesson>(`${LESSONS}/${lesson.id}/${action}`, {
      method: "POST",
      body: { updated_at: lesson.updated_at },
    }),
  remove: (lesson: Pick<Lesson, "id" | "updated_at">) =>
    apiFetch<void>(
      `${LESSONS}/${lesson.id}?${new URLSearchParams({ updated_at: lesson.updated_at })}`,
      { method: "DELETE" },
    ),
};

/** Upload an image or audio file for a card. The same file uploaded twice is stored once. */
export function uploadMedia(file: File): Promise<Asset> {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<Asset>("/api/admin/media", { method: "POST", body: form });
}
