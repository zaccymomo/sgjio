import { apiFetch } from "@sgjio/ui";

export type AptitudeOption = { id: string; text: string };
export type AptitudeQuestion = {
  id: string;
  topic_id: string;
  topic_name: string;
  level: number;
  prompt: string;
  options: AptitudeOption[];
  correct_option_id: string;
  is_active: boolean;
  updated_at: string;
};
export type AptitudeBank = {
  ready: boolean;
  topics: Array<{
    topic_id: string;
    topic_name: string;
    ready: boolean;
    counts_by_level: Record<string, number>;
  }>;
  questions: AptitudeQuestion[];
};
export type AptitudeFields = {
  topic_id: string;
  level?: number;
  prompt: string;
  options: Array<AptitudeOption & { correct: boolean }>;
  is_active: boolean;
};

const URL = "/api/admin/aptitude-questions";
export const aptitudeApi = {
  bank: () => apiFetch<AptitudeBank>(URL),
  create: (fields: AptitudeFields) =>
    apiFetch<AptitudeQuestion>(URL, { method: "POST", body: fields }),
  update: (id: string, fields: Omit<AptitudeFields, "level">) =>
    apiFetch<AptitudeQuestion>(`${URL}/${id}`, { method: "PATCH", body: fields }),
};
