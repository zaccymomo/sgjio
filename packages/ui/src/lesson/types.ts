/**
 * What a lesson is, for both front ends (SCRUM-19). Mirrors app/lesson_doc.py and the lesson
 * schemas in api/app/schemas.py: a change to a lesson's fields starts there and here.
 *
 * A lesson's content is a deck of cards. Every card and question has a `type`, so later
 * formats (chat threads, hotspot scenes, comics; ordering or matching questions) are new
 * kinds in the same deck.
 */

export type Option = {
  id: string;
  text: string;
  correct: boolean;
  /** Shown when a learner picks this option and it is wrong. */
  why_not: string;
};

export type ChoiceQuestion = {
  type: "choice";
  id: string;
  options: Option[];
  /** Shown after answering, right or wrong. */
  explanation: string;
  /** Whether learners see the options in a random order. */
  shuffle: boolean;
};

export type Question = ChoiceQuestion;

export type ImageRef = { asset_id: string; alt: string };
export type AudioRef = { asset_id: string; transcript: string };

export type StoryCard = {
  type: "story";
  id: string;
  /** Markdown, with at most one {{blank}}. */
  text: string;
  image: ImageRef | null;
  audio: AudioRef | null;
  question: Question | null;
};

export type Card = StoryCard;

export type LessonDoc = { cards: Card[] };

/** An image or audio file, as every lesson response carries it in `assets`. */
export type Asset = {
  id: string;
  kind: "image" | "audio";
  mime: string;
  url: string;
  size: number;
  width: number | null;
  height: number | null;
  duration_ms: number | null;
  /** A tiny blurred copy, as a data: URL. */
  placeholder: string | null;
  /** The image's main colour, as #rrggbb. */
  color: string | null;
  filename: string;
};

export type Assets = Record<string, Asset>;

export type Issue = {
  severity: "blocker" | "warning";
  code: string;
  message: string;
  card_id: string | null;
  /** "text", "image", "audio", "question", "question.explanation", "question.options" or
   * "question.options.<option id>". */
  field: string | null;
};

export type LessonStats = {
  cards: number;
  questions: number;
  scored_questions: number;
  words: number;
  audio_seconds: number;
  reading_seconds: number;
};

// --- What a learner sees -------------------------------------------------------------------

/** An option as a learner receives it: which one is right stays on the server. */
export type LearnerOption = { id: string; text: string };

export type LearnerQuestion = {
  type: "choice";
  id: string;
  options: LearnerOption[];
  /** False for a one-option tap, which always succeeds and isn't counted. */
  scored: boolean;
};

export type LearnerCard = Omit<StoryCard, "question"> & { question: LearnerQuestion | null };

/** What checking an answer tells the learner. */
export type CheckResult = {
  correct: boolean;
  correct_option_id: string;
  /** Why the chosen option isn't the norm, when it is wrong and the lesson says. */
  why_not: string;
  explanation: string;
};

export type CheckAnswer = (questionId: string, optionId: string) => Promise<CheckResult>;
