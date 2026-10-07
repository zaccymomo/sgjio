/**
 * What the lesson editor's formatting buttons do to the text (SCRUM-64 AC3, SCRUM-19): bold,
 * italics, lists and headings, written as Markdown, and the blank a question fills.
 *
 * Pure functions, so they can be tested without a browser. Each returns the part of the text
 * to replace and where the selection should end up, rather than the whole new text, so the
 * editor can make the change through the browser and keep undo working.
 */

export type Format = "heading" | "bold" | "italic" | "bullets" | "numbers";

/** Replace `value.slice(from, to)` with `insert`, then select `selectionStart..End`. */
export type Edit = {
  from: number;
  to: number;
  insert: string;
  selectionStart: number;
  selectionEnd: number;
};

/** Text that bold and italic put in when nothing is selected, selected so typing replaces it. */
export const BOLD_PLACEHOLDER = "bold text";
export const ITALIC_PLACEHOLDER = "italic text";

const HEADING = /^#{1,6}\s+/;
const BULLET = /^[-*+]\s+/;
const NUMBER = /^\d+[.)]\s+/;

/** The new text after an edit. What the editor falls back to if the browser can't help. */
export function applyEdit(value: string, edit: Edit): string {
  return value.slice(0, edit.from) + edit.insert + value.slice(edit.to);
}

export function formatEdit(format: Format, value: string, start: number, end: number): Edit {
  if (format === "bold") return wrapEdit("**", BOLD_PLACEHOLDER, value, start, end);
  if (format === "italic") return wrapEdit("*", ITALIC_PLACEHOLDER, value, start, end);
  return lineEdit(format, value, start, end);
}

/** Put `token` (the blank) where the cursor is, replacing any selection. */
export function insertEdit(token: string, value: string, start: number, end: number): Edit {
  const before = start > 0 && !/\s/.test(value[start - 1]) ? " " : "";
  const after = end < value.length && !/[\s.,!?;:]/.test(value[end]) ? " " : "";
  const insert = `${before}${token}${after}`;
  const cursor = start + insert.length;
  return { from: start, to: end, insert, selectionStart: cursor, selectionEnd: cursor };
}

/** Wrap the selection in `marker` (** or *), or unwrap it if it already is. */
function wrapEdit(
  marker: string,
  placeholder: string,
  value: string,
  start: number,
  end: number,
): Edit {
  // Leave out spaces at the edges of the selection (a double-click often takes one), as
  // "** word**" is not bold in Markdown.
  while (start < end && /\s/.test(value[start])) start++;
  while (end > start && /\s/.test(value[end - 1])) end--;

  const size = marker.length;
  const wrapped =
    value.slice(start - size, start) === marker &&
    value.slice(end, end + size) === marker &&
    // Italic inside bold is not italic: "**word**" is not "*word*" with extra stars.
    (size === 2 || (value[start - 2] !== "*" && value[end + 1] !== "*"));
  if (wrapped) {
    const inner = value.slice(start, end);
    return {
      from: start - size,
      to: end + size,
      insert: inner,
      selectionStart: start - size,
      selectionEnd: end - size,
    };
  }
  const inner = start === end ? placeholder : value.slice(start, end);
  return {
    from: start,
    to: end,
    insert: `${marker}${inner}${marker}`,
    selectionStart: start + size,
    selectionEnd: start + size + inner.length,
  };
}

/**
 * Headings and lists apply to whole lines: every line the selection touches. If every
 * non-empty line already has the format, it is taken off instead, so the button toggles.
 */
function lineEdit(
  format: Exclude<Format, "bold" | "italic">,
  value: string,
  start: number,
  end: number,
) {
  const from = value.lastIndexOf("\n", start - 1) + 1;
  // A selection ending just after a line break does not include the next line.
  const lastChar = end > start && value[end - 1] === "\n" ? end - 1 : end;
  const lineEnd = value.indexOf("\n", lastChar);
  const to = lineEnd === -1 ? value.length : lineEnd;
  const lines = value.slice(from, to).split("\n");

  const marker = { heading: HEADING, bullets: BULLET, numbers: NUMBER }[format];
  const filled = lines.filter((line) => line.trim() !== "");
  const removing = filled.length > 0 && filled.every((line) => marker.test(line));

  let count = 0;
  const edited = lines.map((line) => {
    if (removing) return line.replace(marker, "");
    // Leave blank lines between items alone, unless the selection is only a blank line.
    if (line.trim() === "" && filled.length > 0) return line;
    // Swap rather than stack: a bullet made a heading loses its "- ".
    const text = line.replace(HEADING, "").replace(BULLET, "").replace(NUMBER, "");
    if (format === "heading") return `## ${text}`;
    if (format === "bullets") return `- ${text}`;
    count += 1;
    return `${count}. ${text}`;
  });
  const insert = edited.join("\n");

  if (start === end && lines.length === 1) {
    // A cursor keeps its place in the line's text; one inside the old marker goes to the
    // start of the text.
    const inText = Math.max(0, start - from - markerLength(lines[0]));
    const cursor = from + markerLength(edited[0]) + inText;
    return { from, to, insert, selectionStart: cursor, selectionEnd: cursor };
  }
  return { from, to, insert, selectionStart: from, selectionEnd: from + insert.length };
}

/** The length of a line's heading or list marker, or 0 if it has none. */
function markerLength(line: string): number {
  return line.length - line.replace(HEADING, "").replace(BULLET, "").replace(NUMBER, "").length;
}
