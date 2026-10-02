/**
 * Estimated reading time for a lesson's text (SCRUM-64 AC4).
 *
 * Worked out in the browser for now, as a guide while writing. It is a pure function of the
 * Markdown, so if the team decides the limit should block publishing (an open decision in
 * SCRUM-64), the same rule can move to the server unchanged.
 */

/** A common estimate for reading on screen. */
export const WORDS_PER_MINUTE = 200;

/** Lessons should take under 2 minutes to read (CLAUDE.md, "Product rules"). */
export const READING_LIMIT_MINUTES = 2;

export type ReadingTime = {
  words: number;
  /** Rounded up, so the label and the warning always agree. */
  minutes: number;
  /** Over the limit: worth a warning, never a reason to refuse a save. */
  overLimit: boolean;
};

/**
 * Counts words in the text a reader sees. Most Markdown syntax (#, **, "- ") has no letters
 * or digits, so it is never counted; numbered-list markers ("1.") are taken off first, and a
 * link counts its text, not its address.
 */
export function countWords(markdown: string): number {
  const visible = markdown
    .replace(/^\s*\d+[.)]\s+/gm, "")
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1");
  return visible.match(/[\p{L}\p{N}]+(?:['’-][\p{L}\p{N}]+)*/gu)?.length ?? 0;
}

export function readingTime(markdown: string): ReadingTime {
  const words = countWords(markdown);
  const minutes = Math.ceil(words / WORDS_PER_MINUTE);
  return { words, minutes, overLimit: minutes > READING_LIMIT_MINUTES };
}
