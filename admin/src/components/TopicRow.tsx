import { Button } from "@sgjio/ui";
import { Folder } from "lucide-react";

import { lessonSummary, type Topic } from "../lib/topics";

// Equal-width buttons across a phone, compact ones beside the name from 640px up.
const buttonClass = "flex-1 sm:h-9 sm:flex-none";

/**
 * One topic in a list. On a phone the name and counts sit above full-width buttons; from
 * 640px up the buttons move to the right of the row.
 *
 * The buttons carry the topic name in their label, so a screen reader hears "Rename
 * Singlish" rather than the same word over and over.
 */
export function TopicRow({
  topic,
  busy,
  onRename,
  onRemove,
  onRestore,
}: {
  topic: Topic;
  /** A request for this topic is running. */
  busy?: boolean;
  onRename: () => void;
  /** Archive, or delete when the topic has no lessons. Not used for archived topics. */
  onRemove: () => void;
  /** Only for archived topics. */
  onRestore: () => void;
}) {
  const archived = topic.archived_at !== null;
  const empty = topic.lesson_count === 0;

  return (
    <li className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
      <div className="flex min-w-0 items-start gap-3">
        <Folder
          className={
            archived ? "mt-0.5 size-4 shrink-0 text-subtle" : "mt-0.5 size-4 shrink-0 text-brand"
          }
          aria-hidden
        />
        <div className="min-w-0">
          <p className="text-sm font-semibold break-words text-ink">{topic.name}</p>
          <p className="mt-0.5 text-caption text-muted">{lessonSummary(topic)}</p>
        </div>
      </div>

      <div className="flex gap-2 sm:shrink-0">
        {archived && (
          <Button
            className={buttonClass}
            loading={busy}
            onClick={onRestore}
            aria-label={`Restore ${topic.name}`}
          >
            Restore
          </Button>
        )}
        <Button
          variant="secondary"
          className={buttonClass}
          disabled={busy}
          onClick={onRename}
          aria-label={`Rename ${topic.name}`}
        >
          Rename
        </Button>
        {!archived && (
          <Button
            variant="secondary"
            className={buttonClass}
            disabled={busy}
            onClick={onRemove}
            aria-label={`${empty ? "Delete" : "Archive"} ${topic.name}`}
          >
            {empty ? "Delete" : "Archive"}
          </Button>
        )}
      </div>
    </li>
  );
}
