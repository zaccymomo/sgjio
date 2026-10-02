import { cn } from "@sgjio/ui";
import { FileText } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import type { LessonSummary } from "../lib/content";
import { lessonTitle } from "../lib/filter";
import { formatDateTime, formatRelative } from "../lib/format";
import { StatusBadge } from "./StatusBadge";

/**
 * One lesson on a single line: title on the left, then its status and when it was last
 * updated in fixed-width columns before the ⋯ menu, so they line up down the list (SCRUM-66
 * AC1). On a phone the status and time wrap under the title, and the file icon is dropped
 * to leave the title more room. The title opens the
 * lesson (AC4). The drag handle and ⋯ menu are optional, so the same row serves reorderable
 * lists, archived topics and the flat "recently updated" list.
 */
export function LessonRow({
  lesson,
  handle,
  menu,
  topicLabel,
}: {
  lesson: LessonSummary;
  /** The drag handle, or a spacer of the same width so titles line up. */
  handle?: ReactNode;
  /** The ⋯ menu (RowMenu). */
  menu?: ReactNode;
  /** The topic's name, for lists that are not grouped by topic. */
  topicLabel?: string;
}) {
  const untitled = lesson.title.trim() === "";

  return (
    <div className={cn("flex items-center gap-1 py-1 pr-1", !handle && "pl-3", !menu && "pr-4")}>
      {handle}
      <div className="flex min-w-0 flex-1 flex-col gap-x-4 gap-y-1 py-2 sm:flex-row sm:items-center">
        <div className="flex min-w-0 flex-1 gap-2.5">
          <FileText className="mt-0.5 hidden size-4 shrink-0 text-subtle sm:block" aria-hidden />
          <div className="flex min-w-0 flex-col gap-0.5">
            <Link
              to={`/lessons/${lesson.id}`}
              className={cn(
                "w-fit rounded-sm text-sm break-words hover:underline",
                "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
                untitled ? "text-muted italic" : "text-ink",
              )}
            >
              {lessonTitle(lesson)}
            </Link>
            {topicLabel && <p className="text-caption text-muted">{topicLabel}</p>}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2 sm:gap-4">
          <span className="sm:w-24">
            <StatusBadge status={lesson.status} />
          </span>
          <span className="text-caption text-subtle sm:hidden" aria-hidden>
            ·
          </span>
          <span className="text-caption text-muted sm:w-20 sm:text-right">
            <span className="sr-only">Updated </span>
            <time
              dateTime={lesson.updated_at}
              title={`Updated ${formatDateTime(lesson.updated_at)}`}
            >
              {formatRelative(lesson.updated_at)}
            </time>
          </span>
        </div>
      </div>
      {menu}
    </div>
  );
}
