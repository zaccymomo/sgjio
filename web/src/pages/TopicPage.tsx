import { Placeholder } from "@sgjio/ui";
import { ChevronLeft } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

/**
 * Where a progress circle leads (SCRUM-43 AC9). The lesson list itself is SCRUM-53.
 *
 * The back link and the browser's back button both return to the landing page, which is
 * SCRUM-53 AC4.
 */
export function TopicPage() {
  // SCRUM-53 reads the topic id with useParams and loads the lesson list from the server.
  const { state } = useLocation();
  const topicName = (state as { topicName?: string } | null)?.topicName;

  return (
    <div className="flex flex-col gap-4">
      <Link
        to="/"
        className="inline-flex w-fit items-center gap-1 rounded-sm text-sm font-medium text-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
      >
        <ChevronLeft className="size-4" aria-hidden />
        Your progress
      </Link>

      <h1 className="text-[22px] font-bold text-ink">{topicName ?? "Topic"}</h1>

      <Placeholder story="SCRUM-53" title="Lessons in this topic">
        This topic&rsquo;s lessons, showing which ones you have completed (SCRUM-54). Selecting one
        opens the lesson with its quiz question at the end (SCRUM-58, SCRUM-15).
      </Placeholder>
    </div>
  );
}
