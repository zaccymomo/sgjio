import { apiFetch } from "@sgjio/ui";

export type QuizQuestion = {
  id: string;
  topic: string;
  level: number;
  prompt: string;
  options: Array<{ id: string; text: string }>;
};
export type QuizResult = { level: number; correct: number; total: number; taken_at: string };
export const aptitudeApi = {
  start: () => apiFetch<{ questions: QuizQuestion[] }>("/api/aptitude/start", { method: "POST" }),
  submit: (answers: Array<{ question_id: string; option_id: string }>) =>
    apiFetch<QuizResult>("/api/aptitude/submit", { method: "POST", body: { answers } }),
  skip: () => apiFetch<void>("/api/aptitude/skip", { method: "POST" }),
  latest: () => apiFetch<QuizResult>("/api/aptitude/latest"),
};
