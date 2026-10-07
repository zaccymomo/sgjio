import type { Card, ChoiceQuestion, LessonDoc, Option } from "@sgjio/ui/lesson";

/**
 * Changing a lesson's deck in the editor (SCRUM-19). Pure functions on the document, so every
 * change is a new document and the editor's state, autosave and live preview all follow.
 *
 * Ids are made here, so a card keeps its id from the moment it is added and the editor never
 * has to wait for the server to know which card is which.
 */

const ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";

export function newId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(8));
  return Array.from(bytes, (byte) => ALPHABET[byte % ALPHABET.length]).join("");
}

export function newOption(text = "", correct = false): Option {
  return { id: newId(), text, correct, why_not: "" };
}

export function newQuestion(options = 3): ChoiceQuestion {
  return {
    type: "choice",
    id: newId(),
    options: Array.from({ length: options }, (_, n) => newOption("", n === 0)),
    explanation: "",
    shuffle: true,
  };
}

export type Preset = "story" | "question";

/** A new card. A question card starts with a blank and three options, the first marked
 * correct, since that is what most question cards are. */
export function newCard(preset: Preset = "story"): Card {
  return {
    type: "story",
    id: newId(),
    text: preset === "question" ? "{{blank}}" : "",
    image: null,
    audio: null,
    question: preset === "question" ? newQuestion() : null,
  };
}

/** A copy with fresh ids throughout, since ids must be unique within a lesson. */
export function duplicateCard(card: Card): Card {
  return {
    ...card,
    id: newId(),
    question: card.question
      ? {
          ...card.question,
          id: newId(),
          options: card.question.options.map((option) => ({ ...option, id: newId() })),
        }
      : null,
  };
}

export function updateCard(doc: LessonDoc, id: string, change: Partial<Card>): LessonDoc {
  return { cards: doc.cards.map((card) => (card.id === id ? { ...card, ...change } : card)) };
}

export function updateQuestion(
  doc: LessonDoc,
  cardId: string,
  change: Partial<ChoiceQuestion>,
): LessonDoc {
  return {
    cards: doc.cards.map((card) =>
      card.id === cardId && card.question
        ? { ...card, question: { ...card.question, ...change } }
        : card,
    ),
  };
}

export function insertCard(doc: LessonDoc, card: Card, at: number): LessonDoc {
  const cards = [...doc.cards];
  cards.splice(Math.min(Math.max(at, 0), cards.length), 0, card);
  return { cards };
}

export function removeCard(doc: LessonDoc, id: string): LessonDoc {
  return { cards: doc.cards.filter((card) => card.id !== id) };
}

export function reorderCards(doc: LessonDoc, ids: string[]): LessonDoc {
  const byId = new Map(doc.cards.map((card) => [card.id, card]));
  return { cards: ids.flatMap((id) => byId.get(id) ?? []) };
}

/** Mark one option correct and every other not: there is only ever one right answer
 * (SCRUM-19 AC2). */
export function markCorrect(question: ChoiceQuestion, optionId: string): Option[] {
  return question.options.map((option) => ({ ...option, correct: option.id === optionId }));
}

/** Plain words for a card in lists: its text without Markdown, or what it holds. */
export function cardLabel(card: Card): string {
  const text = card.text
    .replace(/\{\{\s*blank\s*\}\}/g, "\u0000")
    .replace(/[*_#>`[\]()-]/g, " ")
    .replace(/\s+/g, " ")
    .replace("\u0000", "___")
    .trim();
  if (text) return text;
  if (card.image) return "Image";
  if (card.audio) return "Audio";
  return "Empty card";
}
