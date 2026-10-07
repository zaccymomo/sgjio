import { cn } from "@sgjio/ui";
import { useId } from "react";

import type { Topic } from "../lib/content";
import { MAX_SUMMARY, MAX_TITLE } from "../lib/lessons";

const NO_TOPIC = "";

/**
 * A lesson's own details at the top of the editor (SCRUM-19, SCRUM-64): its title, written
 * large like a document's, its topic and a one-line summary. Any may be empty in a draft;
 * the title and topic are needed to publish (SCRUM-56).
 */
export function LessonDetails({
  title,
  summary,
  topicId,
  topics,
  savedTopicId,
  published,
  titleError,
  topicError,
  onChange,
}: {
  title: string;
  summary: string;
  topicId: string | null;
  /** Every topic, archived ones included, in order. */
  topics: Topic[];
  /** The topic the lesson is saved in, offered even if it has since been archived. */
  savedTopicId: string | null;
  /** Published at some point: it always keeps a topic, and moving it shows at once. */
  published: boolean;
  titleError?: string;
  topicError?: string;
  onChange: (change: { title?: string; summary?: string; topic_id?: string | null }) => void;
}) {
  const titleId = useId();
  const summaryId = useId();
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <label htmlFor={titleId} className="sr-only">
        Title
      </label>
      <input
        id={titleId}
        value={title}
        onChange={(event) => onChange({ title: event.target.value })}
        maxLength={MAX_TITLE}
        placeholder="Untitled lesson"
        autoComplete="off"
        aria-invalid={titleError ? true : undefined}
        title={titleError}
        className={cn(
          "-mx-1 w-full min-w-0 rounded-sm bg-transparent px-1 text-2xl font-bold text-ink outline-none placeholder:text-subtle focus:bg-white focus:ring-2 focus:ring-ink/10",
          titleError && "placeholder:text-danger/70",
        )}
      />
      <div className="flex flex-wrap items-center gap-2">
        <TopicSelect
          value={topicId}
          onChange={(topic_id) => onChange({ topic_id })}
          topics={topics}
          savedTopicId={savedTopicId}
          published={published}
          error={topicError}
        />
        <label htmlFor={summaryId} className="sr-only">
          Summary
        </label>
        <input
          id={summaryId}
          value={summary}
          onChange={(event) => onChange({ summary: event.target.value })}
          maxLength={MAX_SUMMARY}
          placeholder="Add a one-line summary, shown in lesson lists"
          className="h-8 min-w-0 flex-1 basis-64 rounded-sm border border-transparent bg-transparent px-2 text-sm text-ink outline-none placeholder:text-subtle hover:border-line focus:border-ink focus:bg-white"
        />
      </div>
    </div>
  );
}

/**
 * Active topics in order, then "No topic yet" for a lesson never published. New lessons
 * cannot go into an archived topic, but a lesson already in one keeps it as an option,
 * marked as archived.
 */
function TopicSelect({
  value,
  onChange,
  topics,
  savedTopicId,
  published,
  error,
}: {
  value: string | null;
  onChange: (topicId: string | null) => void;
  topics: Topic[];
  savedTopicId: string | null;
  published: boolean;
  error?: string;
}) {
  const id = useId();
  const options = topics.filter(
    (topic) => topic.archived_at === null || topic.id === savedTopicId || topic.id === value,
  );
  return (
    <span className="flex items-center gap-1.5">
      <label htmlFor={id} className="text-xs font-semibold text-muted">
        Topic
      </label>
      <select
        id={id}
        value={value ?? NO_TOPIC}
        onChange={(event) => onChange(event.target.value === NO_TOPIC ? null : event.target.value)}
        aria-invalid={error ? true : undefined}
        title={
          error ??
          (published
            ? "Moving a published lesson to another topic takes effect straight away."
            : "A lesson needs a topic before it can be published.")
        }
        className={cn(
          "h-8 rounded-sm border bg-white px-2 text-sm font-medium text-ink outline-none focus:ring-2",
          error
            ? "border-danger text-danger focus:ring-danger/20"
            : "border-line focus:border-ink focus:ring-ink/10",
        )}
      >
        {!published && <option value={NO_TOPIC}>No topic yet</option>}
        {options.map((topic) => (
          <option key={topic.id} value={topic.id}>
            {topic.name}
            {topic.archived_at ? " (archived)" : ""}
          </option>
        ))}
      </select>
    </span>
  );
}
