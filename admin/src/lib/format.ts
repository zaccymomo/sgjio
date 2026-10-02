import type { Topic } from "./content";

// Kept in the admin portal rather than packages/ui, whose format helpers are being
// changed on another branch.

const DATE_TIME = new Intl.DateTimeFormat("en-SG", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

const DATE = new Intl.DateTimeFormat("en-SG", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

/** "2 Oct 2026, 3:45 pm" in the viewer's local time. */
export function formatDateTime(iso: string): string {
  return DATE_TIME.format(new Date(iso));
}

/** "2 Oct 2026" in the viewer's local time. */
export function formatDate(iso: string): string {
  return DATE.format(new Date(iso));
}

const RELATIVE = new Intl.RelativeTimeFormat("en-SG", { numeric: "auto" });

const DAY_MS = 24 * 60 * 60 * 1000;

/** Local midnight at the start of the date's day. */
function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

/**
 * "just now", "5 minutes ago", "3 hours ago" within the day; then calendar days, so
 * 11:35 pm two nights ago is "2 days ago", not "yesterday". From a week back, the date
 * ("2 Oct 2026"), which reads better than "5 weeks ago" in a list of lessons.
 */
export function formatRelative(iso: string, now: Date = new Date()): string {
  const then = new Date(iso);
  const minutes = Math.floor((now.getTime() - then.getTime()) / 60_000);
  if (minutes < 1) return "just now";
  // Round, as midnight-to-midnight can be 23 or 25 hours across a daylight-saving change.
  const days = Math.round((startOfDay(now) - startOfDay(then)) / DAY_MS);
  if (days === 0) {
    return minutes < 60
      ? RELATIVE.format(-minutes, "minute")
      : RELATIVE.format(-Math.floor(minutes / 60), "hour");
  }
  if (days < 7) return RELATIVE.format(-days, "day");
  return formatDate(iso);
}

/** "1 lesson", "3 lessons". */
export function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

/** "3 lessons · 2 published", from the server's counts over every status. */
export function topicSummary(topic: Topic): string {
  if (topic.lesson_count === 0) return "No lessons yet";
  return `${plural(topic.lesson_count, "lesson")} · ${topic.published_count} published`;
}
