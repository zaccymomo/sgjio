// Lessons as decks of cards (SCRUM-19, SCRUM-65): the types both front ends share, and the
// deck learners use and the admin portal previews with. Imported separately from the rest of
// @sgjio/ui, as "@sgjio/ui/lesson", so pages without lessons don't load the deck's libraries.

export {
  BLANK_PATTERN,
  BLANK_TOKEN,
  checkLocally,
  correctOption,
  hasBlank,
  isScored,
  readingLabel,
  toLearnerCards,
} from "./doc";
export { LessonDeck, type DeckLesson, type DeckSummary } from "./LessonDeck";
export { LessonText } from "./LessonText";
export { AudioPlayer, CardImage } from "./media";
export { tint } from "./tint";
export { useMuted } from "./sound";
export type * from "./types";
