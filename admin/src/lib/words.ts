/**
 * Counting the words a reader sees in a card's text, for the editor's word count
 * (SCRUM-19). The same rule as count_words in api/app/lesson_doc.py, which decides the
 * reading-time checks: most Markdown syntax (**, "- ") has no letters or digits, so it is
 * never counted; numbered-list markers ("1.") are taken off first, and a link counts its
 * text, not its address.
 */
export function countWords(markdown: string): number {
  const visible = markdown
    .replace(/^\s*\d+[.)]\s+/gm, "")
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1");
  return visible.match(/[\p{L}\p{N}]+(?:['’-][\p{L}\p{N}]+)*/gu)?.length ?? 0;
}
