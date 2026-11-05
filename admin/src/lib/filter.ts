import type { LessonStatus, LessonSummary, Topic } from "./content";

/**
 * What the content page shows for a given search and filters (SCRUM-66 AC2). Pure, so the
 * rules live in one place:
 *
 * - search matches topic names and lesson titles, ignoring case and accents
 * - a topic whose name matches shows all its lessons; a lesson whose title matches keeps
 *   its topic on screen, opened, showing only the matching lessons
 * - the status, level and topic filters apply on top of the search
 * - lessons with no topic form their own group, which no topic name can match
 */

export type StatusFilter = "all" | LessonStatus;
/** "all", or a level from 1 to 5 as text (SCRUM-103 AC3). */
export type LevelFilter = string;
/** "all", "none" (lessons with no topic), or a topic id. */
export type TopicFilter = string;

export type Filters = {
  query: string;
  status: StatusFilter;
  level: LevelFilter;
  topic: TopicFilter;
};

export const NO_FILTERS: Filters = { query: "", status: "all", level: "all", topic: "all" };

export const UNTITLED = "Untitled lesson";

export type Group = {
  /** Null for the lessons with no topic. */
  topic: Topic | null;
  /** The lessons to show, in order. */
  lessons: LessonSummary[];
  /** Every lesson in the group, in order: what a reorder must send. */
  allLessons: LessonSummary[];
};

export type ContentView = {
  filtering: boolean;
  active: Group[];
  noTopic: Group | null;
  archived: Group[];
  /** Every lesson that passes, most recently updated first (SCRUM-66 AC3). */
  recent: LessonSummary[];
  /** How many lessons pass in the topic view, for the result count. */
  lessonCount: number;
};

export function isFiltering(filters: Filters): boolean {
  return (
    filters.query.trim() !== "" ||
    filters.status !== "all" ||
    filters.level !== "all" ||
    filters.topic !== "all"
  );
}

/** Lower case, accents removed, so "cafe" finds "Café". */
export function normalise(text: string): string {
  return text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().trim();
}

export function lessonTitle(lesson: Pick<LessonSummary, "title">): string {
  return lesson.title.trim() || UNTITLED;
}

/** Stable, so lessons sharing a position keep the server's order (creation time). */
function inOrder(lessons: LessonSummary[]): LessonSummary[] {
  return lessons
    .map((lesson, index) => ({ lesson, index }))
    .sort((a, b) => a.lesson.position - b.lesson.position || a.index - b.index)
    .map(({ lesson }) => lesson);
}

export function viewContent(
  topics: Topic[],
  lessons: LessonSummary[],
  filters: Filters,
): ContentView {
  const query = normalise(filters.query);
  const filtering = isFiltering(filters);
  const statusMatches = (lesson: LessonSummary) =>
    (filters.status === "all" || lesson.status === filters.status) &&
    (filters.level === "all" || String(lesson.level) === filters.level);
  const titleMatches = (lesson: LessonSummary) => normalise(lessonTitle(lesson)).includes(query);

  const byTopic = new Map<string | null, LessonSummary[]>();
  for (const lesson of lessons) {
    const group = byTopic.get(lesson.topic_id) ?? [];
    group.push(lesson);
    byTopic.set(lesson.topic_id, group);
  }

  function group(topic: Topic | null): Group | null {
    const key = topic?.id ?? null;
    if (filters.topic !== "all" && filters.topic !== (key ?? "none")) return null;

    const allLessons = inOrder(byTopic.get(key) ?? []);
    const nameMatches = query !== "" && topic !== null && normalise(topic.name).includes(query);
    const passing = allLessons.filter(
      (lesson) => statusMatches(lesson) && (query === "" || nameMatches || titleMatches(lesson)),
    );
    // A topic stays on screen without lessons only when nothing asked about lessons: no
    // status or level filter, and either no search or a search its name matches.
    const needsLessons =
      filters.status !== "all" || filters.level !== "all" || (query !== "" && !nameMatches);
    if (needsLessons && passing.length === 0) return null;
    return { topic, lessons: passing, allLessons };
  }

  const ordered = [...topics].sort((a, b) => a.position - b.position);
  const active = ordered.flatMap((topic) => {
    const result = topic.archived_at === null ? group(topic) : null;
    return result ? [result] : [];
  });
  const archived = ordered.flatMap((topic) => {
    const result = topic.archived_at !== null ? group(topic) : null;
    return result ? [result] : [];
  });
  const noTopic = byTopic.has(null) ? group(null) : null;

  const topicNames = new Map(topics.map((topic) => [topic.id, normalise(topic.name)]));
  const recent = lessons
    .filter((lesson) => {
      if (filters.topic !== "all" && filters.topic !== (lesson.topic_id ?? "none")) return false;
      if (!statusMatches(lesson)) return false;
      if (query === "") return true;
      const topicName = lesson.topic_id ? topicNames.get(lesson.topic_id) : undefined;
      return titleMatches(lesson) || (topicName?.includes(query) ?? false);
    })
    // Compared as times, not strings: the fraction of a second varies in length.
    .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at));

  const lessonCount = [...active, ...archived, ...(noTopic ? [noTopic] : [])].reduce(
    (total, { lessons: shown }) => total + shown.length,
    0,
  );

  return { filtering, active, noTopic, archived, recent, lessonCount };
}
