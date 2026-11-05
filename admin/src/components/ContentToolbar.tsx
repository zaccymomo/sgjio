import { Button, cn, TextField } from "@sgjio/ui";
import { X } from "lucide-react";
import { useId, type ReactNode } from "react";

import { STATUS_LABELS, type Topic } from "../lib/content";
import { NO_FILTERS, type Filters, type StatusFilter } from "../lib/filter";
import { LEVEL_DESCRIPTIONS, LEVELS, levelLabel } from "../lib/levels";

export type View = "topics" | "recent";

const VIEWS: Array<{ value: View; label: string }> = [
  { value: "topics", label: "Topic order" },
  { value: "recent", label: "Recently updated" },
];

/** Search, the status, level (SCRUM-103 AC3) and topic filters (SCRUM-66 AC2), and the
 * choice of view (AC3). */
export function ContentToolbar({
  filters,
  onFiltersChange,
  filtering,
  view,
  onViewChange,
  topics,
  hasLessonsWithoutTopic,
  result,
}: {
  filters: Filters;
  onFiltersChange: (filters: Filters) => void;
  filtering: boolean;
  view: View;
  onViewChange: (view: View) => void;
  topics: Topic[];
  hasLessonsWithoutTopic: boolean;
  /** "3 lessons in 2 topics", read out as it changes. */
  result: string;
}) {
  const active = topics.filter((topic) => topic.archived_at === null);
  const archived = topics.filter((topic) => topic.archived_at !== null);

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-line bg-white p-3 sm:p-4">
      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_33rem]">
        <TextField
          label="Search topics and lessons"
          type="search"
          placeholder="Topic name or lesson title"
          value={filters.query}
          onChange={(event) => onFiltersChange({ ...filters, query: event.target.value })}
        />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <Select
            label="Status"
            value={filters.status}
            onChange={(status) => onFiltersChange({ ...filters, status: status as StatusFilter })}
          >
            <option value="all">All statuses</option>
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
          <Select
            label="Level"
            value={filters.level}
            onChange={(level) => onFiltersChange({ ...filters, level })}
          >
            <option value="all">All levels</option>
            {LEVELS.map((level) => (
              <option key={level} value={String(level)} title={LEVEL_DESCRIPTIONS[level]}>
                {levelLabel(level)}
              </option>
            ))}
          </Select>
          <Select
            label="Topic"
            className="col-span-2 sm:col-span-1"
            value={filters.topic}
            onChange={(topic) => onFiltersChange({ ...filters, topic })}
          >
            <option value="all">All topics</option>
            {active.map((topic) => (
              <option key={topic.id} value={topic.id}>
                {topic.name}
              </option>
            ))}
            {hasLessonsWithoutTopic && <option value="none">No topic</option>}
            {archived.length > 0 && (
              <optgroup label="Archived">
                {archived.map((topic) => (
                  <option key={topic.id} value={topic.id}>
                    {topic.name}
                  </option>
                ))}
              </optgroup>
            )}
          </Select>
        </div>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div
          role="group"
          aria-label="View"
          className="flex rounded-md border border-line bg-surface p-0.5 sm:inline-flex"
        >
          {VIEWS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              aria-pressed={view === value}
              onClick={() => onViewChange(value)}
              className={cn(
                "h-8 flex-1 rounded-sm px-3 text-xs font-semibold transition-colors sm:flex-none",
                "focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brand",
                view === value ? "bg-white text-ink shadow-sm" : "text-muted hover:text-ink",
              )}
            >
              {label}
            </button>
          ))}
        </div>
        {filtering && (
          <div className="flex items-center justify-between gap-2 sm:justify-end">
            <p className="text-caption text-muted">{result}</p>
            <Button variant="ghost" size="sm" onClick={() => onFiltersChange(NO_FILTERS)}>
              <X className="size-3.5" aria-hidden />
              Clear filters
            </Button>
          </div>
        )}
        {/* Always present, so screen readers hear the count change as people type. */}
        <p className="sr-only" aria-live="polite">
          {result}
        </p>
      </div>
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  className,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  className?: string;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-xs font-semibold text-ink">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-11 w-full min-w-0 rounded-sm border border-line bg-white px-2.5 text-sm text-ink outline-none focus:border-ink focus:ring-2 focus:ring-ink/10"
      >
        {children}
      </select>
    </div>
  );
}
