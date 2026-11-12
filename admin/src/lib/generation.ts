import { apiFetch } from "@sgjio/ui";

/**
 * AI-drafted lessons (docs/ai-lessons-api.md, "Content"). The administrator asks for a
 * draft; Content sends the request to Generation and, when the lesson comes back, saves it
 * as an ordinary Draft that opens in the lesson editor.
 */

/** Same limit as the API (GenerationRequest in services/content/app/schemas.py). */
export const MAX_NOTES = 2000;
export const CARD_CHOICES = [4, 6, 8] as const;
export type CardChoice = (typeof CARD_CHOICES)[number];

export type GenerationRequest = {
  topic_id: string;
  level: number;
  notes: string;
  cards: CardChoice;
};

export type GenerationJob = {
  id: string;
  status: "requested" | "writing" | "done" | "failed";
  /** The new Draft, once `status` is done. */
  lesson_id: string | null;
  failure: { code: string; message: string } | null;
  left_today: number;
};

export type GenerationQuota = { daily_limit: number; left_today: number };

export const generationApi = {
  quota: () => apiFetch<GenerationQuota>("/api/admin/generation"),
  request: (body: GenerationRequest) =>
    apiFetch<GenerationJob>("/api/admin/lessons/generate", { method: "POST", body }),
  get: (id: string) => apiFetch<GenerationJob>(`/api/admin/generation/${id}`),
};
