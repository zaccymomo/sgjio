/**
 * Lesson levels (SCRUM-103). Lessons and aptitude questions share Level 1 to 5 (Epic 6);
 * the aptitude quiz exempts users from a topic's lessons up to the level they reach there
 * (SCRUM-104). Learners see only the number, on topic pages and their aptitude results.
 *
 * The descriptions keep authors using the scale the same way. They are a first draft for
 * the team to agree (docs/decisions.md); change the wording here.
 */
export const LEVELS = [1, 2, 3, 4, 5] as const;

export type Level = (typeof LEVELS)[number];

export const LEVEL_DESCRIPTIONS: Record<Level, string> = {
  1: "Essentials for your first weeks",
  2: "Everyday situations within a few months",
  3: "Social nuance: tone, indirectness, unwritten rules",
  4: "Less obvious customs most long-term residents learn",
  5: "Insider knowledge: deep Singlish, history, local quirks",
};

export function levelLabel(level: number): string {
  return `Level ${level}`;
}
