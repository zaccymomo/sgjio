import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { cn } from "@sgjio/ui";
import { Check, ChevronDown, Lock } from "lucide-react";
import { useId } from "react";

import type { Topic } from "../lib/content";
import { MAX_SUMMARY, MAX_TITLE } from "../lib/lessons";
import { LEVEL_DESCRIPTIONS, LEVELS, levelLabel, type Level } from "../lib/levels";

const NO_TOPIC = "";

/**
 * A lesson's own details at the top of the editor (SCRUM-19, SCRUM-64): its title, written
 * large like a document's, its topic, its level and a one-line summary. Any but the level
 * may be empty in a draft; the title and topic are needed to publish (SCRUM-56). The level
 * is needed before a new lesson is saved at all, and is fixed once published (SCRUM-103).
 */
export function LessonDetails({
  title,
  summary,
  topicId,
  level,
  topics,
  savedTopicId,
  published,
  titleError,
  topicError,
  levelError,
  onChange,
}: {
  title: string;
  summary: string;
  topicId: string | null;
  level: number | null;
  /** Every topic, archived ones included, in order. */
  topics: Topic[];
  /** The topic the lesson is saved in, offered even if it has since been archived. */
  savedTopicId: string | null;
  /** Published at some point: it always keeps a topic, and moving it shows at once. */
  published: boolean;
  titleError?: string;
  topicError?: string;
  levelError?: string;
  onChange: (change: {
    title?: string;
    summary?: string;
    topic_id?: string | null;
    level?: number;
  }) => void;
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
        <LevelSelect
          value={level}
          onChange={(next) => onChange({ level: next })}
          locked={published}
          error={levelError}
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

/**
 * The lesson's level, 1 to 5 (SCRUM-103). A new lesson starts with none, so the
 * administrator has to choose. It can change until the lesson is first published; after
 * that it is shown but fixed, so learners' exemptions never shift.
 *
 * A menu rather than a native select, so each level can show its description without the
 * control growing as wide as the longest one.
 */
function LevelSelect({
  value,
  onChange,
  locked,
  error,
}: {
  value: number | null;
  onChange: (level: number) => void;
  locked: boolean;
  error?: string;
}) {
  const description = value ? LEVEL_DESCRIPTIONS[value as Level] : undefined;
  if (locked && value !== null) {
    return (
      <span
        className="flex h-8 items-center gap-1.5 rounded-sm bg-black/5 px-2 text-sm font-medium text-ink"
        title={`${description}. A published lesson's level is fixed, so learners' exemptions don't change. To offer it at another level, write a new lesson.`}
      >
        <Lock className="size-3.5 text-muted" aria-hidden />
        {levelLabel(value)}
        <span className="sr-only">, fixed because the lesson has been published</span>
      </span>
    );
  }
  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          aria-label={value ? `Level: ${levelLabel(value)}. Change level` : "Choose a level"}
          aria-invalid={error ? true : undefined}
          title={
            error ??
            (description
              ? `${description}. You can change the level until the lesson is published.`
              : "Choose how advanced this lesson is. You can change it until it's published.")
          }
          className={cn(
            "flex h-8 items-center gap-1 rounded-sm border bg-white px-2 text-sm font-medium outline-none focus-visible:ring-2",
            error
              ? "border-danger text-danger focus-visible:ring-danger/20"
              : "border-line text-ink focus-visible:border-ink focus-visible:ring-ink/10",
            value === null && !error && "text-muted",
          )}
        >
          {value ? levelLabel(value) : "Choose a level"}
          <ChevronDown className="size-3.5 text-muted" aria-hidden />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="start"
          sideOffset={4}
          collisionPadding={8}
          className="z-50 w-80 rounded-md border border-line bg-white p-1 shadow-lg"
        >
          <DropdownMenu.Label className="px-2.5 pt-1.5 pb-1 text-2xs text-muted">
            How advanced is this lesson? You can change it until it&rsquo;s published.
          </DropdownMenu.Label>
          <DropdownMenu.RadioGroup
            value={value ? String(value) : ""}
            onValueChange={(next) => onChange(Number(next))}
          >
            {LEVELS.map((level) => (
              <DropdownMenu.RadioItem
                key={level}
                value={String(level)}
                className="flex cursor-pointer items-start gap-2 rounded-sm px-2.5 py-2 outline-none data-[highlighted]:bg-surface"
              >
                <span className="flex size-4 shrink-0 items-center justify-center pt-0.5">
                  <DropdownMenu.ItemIndicator>
                    <Check className="size-4 text-ink" aria-hidden />
                  </DropdownMenu.ItemIndicator>
                </span>
                <span className="flex flex-col">
                  <span className="text-sm font-semibold text-ink">{levelLabel(level)}</span>
                  <span className="text-caption text-muted">{LEVEL_DESCRIPTIONS[level]}</span>
                </span>
              </DropdownMenu.RadioItem>
            ))}
          </DropdownMenu.RadioGroup>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
