import { apiFetch } from "@sgjio/ui";

import type { LessonStatus } from "./content";

/**
 * What a lesson is, as the editor saves it (SCRUM-64). Mirrors LessonFields in
 * api/app/schemas.py; together with components/LessonForm.tsx these are the places to change
 * when the lesson design changes. `topic_id: null` means no topic yet.
 */
export type LessonFields = {
  title: string;
  content: string;
  topic_id: string | null;
};

/** One lesson as GET /api/admin/lessons/{id} returns it. */
export type Lesson = LessonFields & {
  id: string;
  status: LessonStatus;
  published_at: string | null;
  withdrawn_at: string | null;
  position: number;
  created_at: string;
  updated_at: string;
  /** A draft that has never been published. Only these can be deleted. */
  deletable: boolean;
};

/** Same limits as the API (MAX_LESSON_TITLE and MAX_LESSON_CONTENT in schemas.py). */
export const MAX_TITLE = 200;
export const MAX_CONTENT = 20_000;

export type LessonFieldErrors = Partial<Record<keyof LessonFields, string>>;

export function emptyLesson(topicId: string | null = null): LessonFields {
  return { title: "", content: "", topic_id: topicId };
}

export function fieldsOf(lesson: Lesson): LessonFields {
  return { title: lesson.title, content: lesson.content, topic_id: lesson.topic_id };
}

/** Whether saving `a` would change `b`. Titles are trimmed on save, so compare them so. */
export function sameFields(a: LessonFields, b: LessonFields): boolean {
  return a.title.trim() === b.title.trim() && a.content === b.content && a.topic_id === b.topic_id;
}

/**
 * What can be checked before saving. Empty fields are fine in a draft: they are required
 * only when publishing (SCRUM-56, SCRUM-70).
 */
export function lessonFieldErrors(fields: LessonFields): LessonFieldErrors {
  const errors: LessonFieldErrors = {};
  const title = fields.title.trim();
  if (title.length > MAX_TITLE) {
    errors.title = `Use ${MAX_TITLE} characters or fewer. This title has ${title.length}.`;
  }
  if (fields.content.length > MAX_CONTENT) {
    errors.content =
      `Use ${MAX_CONTENT.toLocaleString("en-SG")} characters or fewer. This text has ` +
      `${fields.content.length.toLocaleString("en-SG")}.`;
  }
  return errors;
}

const LESSONS = "/api/admin/lessons";

/**
 * Saves and deletes send the `updated_at` the editor loaded. If the lesson has changed
 * since, the server refuses with lesson_out_of_date rather than overwrite that change.
 */
export const lessonApi = {
  get: (id: string, signal?: AbortSignal) => apiFetch<Lesson>(`${LESSONS}/${id}`, { signal }),
  create: (fields: LessonFields) =>
    apiFetch<Lesson>(LESSONS, { method: "POST", body: { ...fields, title: fields.title.trim() } }),
  update: (lesson: Lesson, fields: LessonFields) =>
    apiFetch<Lesson>(`${LESSONS}/${lesson.id}`, {
      method: "PATCH",
      body: { ...fields, title: fields.title.trim(), updated_at: lesson.updated_at },
    }),
  remove: (lesson: Lesson) =>
    apiFetch<void>(
      `${LESSONS}/${lesson.id}?${new URLSearchParams({ updated_at: lesson.updated_at })}`,
      { method: "DELETE" },
    ),
};
