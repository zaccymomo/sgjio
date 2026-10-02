import { TextField, cn } from "@sgjio/ui";
import { useId } from "react";

import type { Topic } from "../lib/content";
import { MAX_TITLE, type LessonFieldErrors, type LessonFields } from "../lib/lessons";
import { MarkdownField } from "./MarkdownField";

const NO_TOPIC = "";

/**
 * A lesson's fields in the editor (SCRUM-64): title, topic and text. Together with
 * lib/lessons.ts this is what a lesson "is" on the admin side, so a change to the lesson
 * design (a summary, sections, questions within the text) starts here.
 *
 * Every field may be left empty in a draft.
 */
export function LessonForm({
  value,
  onChange,
  errors,
  topics,
  savedTopicId,
  readOnly,
}: {
  value: LessonFields;
  onChange: (value: LessonFields) => void;
  errors: LessonFieldErrors;
  /** Every topic, archived ones included, in order. */
  topics: Topic[];
  /** The topic the lesson is saved in, offered even if it has since been archived. */
  savedTopicId: string | null;
  readOnly?: boolean;
}) {
  const set = <K extends keyof LessonFields>(key: K, next: LessonFields[K]) =>
    onChange({ ...value, [key]: next });
  const titleLength = value.title.trim().length;

  return (
    <div className="flex flex-col gap-5">
      <TextField
        label="Title"
        value={value.title}
        onChange={(event) => set("title", event.target.value)}
        readOnly={readOnly}
        autoComplete="off"
        error={errors.title}
        hint={`${titleLength} / ${MAX_TITLE} characters`}
      />
      <TopicSelect
        value={value.topic_id}
        onChange={(topicId) => set("topic_id", topicId)}
        topics={topics}
        savedTopicId={savedTopicId}
        error={errors.topic_id}
        readOnly={readOnly}
      />
      <MarkdownField
        label="Lesson text"
        value={value.content}
        onChange={(content) => set("content", content)}
        error={errors.content}
        readOnly={readOnly}
      />
    </div>
  );
}

/**
 * Active topics in order, then "No topic yet". New lessons cannot go into an archived topic,
 * but a lesson already in one keeps it as an option, marked as archived.
 */
function TopicSelect({
  value,
  onChange,
  topics,
  savedTopicId,
  error,
  readOnly,
}: {
  value: string | null;
  onChange: (topicId: string | null) => void;
  topics: Topic[];
  savedTopicId: string | null;
  error?: string;
  readOnly?: boolean;
}) {
  const id = useId();
  const messageId = `${id}-message`;
  const options = topics.filter(
    (topic) => topic.archived_at === null || topic.id === savedTopicId || topic.id === value,
  );
  const selectedArchived = topics.some((topic) => topic.id === value && topic.archived_at);

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-xs font-semibold text-ink">
        Topic
      </label>
      <select
        id={id}
        value={value ?? NO_TOPIC}
        onChange={(event) => onChange(event.target.value === NO_TOPIC ? null : event.target.value)}
        disabled={readOnly}
        aria-invalid={error ? true : undefined}
        aria-describedby={error || !readOnly ? messageId : undefined}
        className={cn(
          "h-11 w-full rounded-sm border bg-white px-2.5 text-sm text-ink outline-none focus:ring-2 disabled:opacity-60 sm:max-w-sm",
          error
            ? "border-danger focus:ring-danger/20"
            : "border-line focus:border-ink focus:ring-ink/10",
        )}
      >
        <option value={NO_TOPIC}>No topic yet</option>
        {options.map((topic) => (
          <option key={topic.id} value={topic.id}>
            {topic.name}
            {topic.archived_at ? " (archived)" : ""}
          </option>
        ))}
      </select>
      {(error || !readOnly) && (
        <p id={messageId} className={cn("text-xs", error ? "text-danger" : "text-muted")}>
          {error ??
            (selectedArchived
              ? "This topic is archived, so users won't see the lesson until it is restored."
              : "A lesson needs a topic before it can be published. A new topic puts the lesson at the end of it.")}
        </p>
      )}
    </div>
  );
}
