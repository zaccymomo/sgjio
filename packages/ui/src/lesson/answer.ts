import type { CheckResult } from "./types";

/** Where a learner is with one question. Kept by the deck, so going back shows it again. */
export type AnswerState = {
  selected: string | null;
  status: "idle" | "checking" | "done";
  result?: CheckResult;
  /** After a wrong answer, once the slot has shaken: the right option moves into place. */
  revealed?: boolean;
  error?: string;
};

export const NO_ANSWER: AnswerState = { selected: null, status: "idle" };
