import { apiFetch } from "@sgjio/ui";

export type QuizAnswer = { question_id: string; option_id: string };
export type QuizQuestion = {
  id: string;
  topic_id: string;
  topic: string;
  level: number;
  prompt: string;
  options: Array<{ id: string; text: string }>;
  topic_index: number;
  topic_count: number;
};
export type QuizStep = { done: boolean; question: QuizQuestion | null };
export type QuizResult = {
  correct: number;
  total: number;
  taken_at: string;
  placements: Array<{ topic_id: string; topic: string; level: number }>;
};

export const aptitudeApi = {
  start: () => apiFetch<QuizStep>("/api/aptitude/start", { method: "POST" }),
  next: (answers: QuizAnswer[]) =>
    apiFetch<QuizStep>("/api/aptitude/next", { method: "POST", body: { answers } }),
  submit: (answers: QuizAnswer[]) =>
    apiFetch<QuizResult>("/api/aptitude/submit", { method: "POST", body: { answers } }),
  skip: () => apiFetch<void>("/api/aptitude/skip", { method: "POST" }),
  result: () => apiFetch<QuizResult>("/api/aptitude/result"),
};
