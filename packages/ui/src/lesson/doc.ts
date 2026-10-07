import type {
  Card,
  CheckAnswer,
  CheckResult,
  LearnerCard,
  LessonDoc,
  Option,
  Question,
} from "./types";

/** The same pattern as BLANK in api/app/lesson_doc.py. */
export const BLANK_PATTERN = /\{\{\s*blank\s*\}\}/;
export const BLANK_TOKEN = "{{blank}}";

export function hasBlank(text: string): boolean {
  return BLANK_PATTERN.test(text);
}

/** The option that is right. A question with one option needs no marking. */
export function correctOption(question: Question): Option | null {
  const marked = question.options.filter((option) => option.correct);
  if (marked.length === 1) return marked[0];
  if (marked.length === 0 && question.options.length === 1) return question.options[0];
  return null;
}

export function isScored(question: Pick<Question, "options">): boolean {
  return question.options.length >= 2;
}

/** A small seeded random generator, so a deck's shuffle stays put while it is open. */
function random(seed: number): () => number {
  let state = seed >>> 0 || 1;
  return () => {
    state ^= state << 13;
    state ^= state >>> 17;
    state ^= state << 5;
    return (state >>> 0) / 4294967296;
  };
}

function shuffled<T>(items: T[], next: () => number): T[] {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(next() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

/**
 * The deck as a learner sees it: which option is right, the "why not" notes and the
 * explanation are left out, and options are shuffled where the question says so.
 *
 * `seed` fixes the shuffle; pass `null` to keep the options in the order they were written,
 * as the editor's live preview does, so options don't jump around while being typed.
 */
export function toLearnerCards(doc: LessonDoc, seed: number | null): LearnerCard[] {
  const next = random(seed ?? 1);
  return doc.cards.map((card: Card) => {
    const question = card.question;
    if (!question) return { ...card, question: null };
    const options = question.options.map(({ id, text }) => ({ id, text }));
    return {
      ...card,
      question: {
        type: question.type,
        id: question.id,
        options: question.shuffle && seed !== null ? shuffled(options, next) : options,
        scored: isScored(question),
      },
    };
  });
}

/**
 * Checks answers against a document in the browser, for previews: nothing is sent or
 * recorded. Learners' answers are checked on the server instead (SCRUM-16 AC1).
 */
export function checkLocally(doc: LessonDoc): CheckAnswer {
  return async (questionId, optionId) => {
    const question = doc.cards.find((card) => card.question?.id === questionId)?.question;
    if (!question) throw new Error(`No question ${questionId} in this lesson.`);
    const answer = correctOption(question);
    const chosen = question.options.find((option) => option.id === optionId);
    const correct = answer !== null && answer.id === optionId;
    const result: CheckResult = {
      correct,
      correct_option_id: answer?.id ?? "",
      why_not: correct ? "" : (chosen?.why_not ?? ""),
      explanation: question.explanation,
    };
    return result;
  };
}

/** "About 1 min", for a reading time in seconds. */
export function readingLabel(seconds: number): string {
  if (seconds < 45) return "Under 1 min";
  return `About ${Math.max(1, Math.round(seconds / 60))} min`;
}
