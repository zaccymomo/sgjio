import { Placeholder } from "@sgjio/ui";
import { ChevronLeft } from "lucide-react";
import { Link } from "react-router-dom";

/**
 * Where a lesson title on the content page leads (SCRUM-66 AC4), so the link does not
 * dead-end. The editor itself is SCRUM-64 for drafts and SCRUM-52 for published lessons.
 */
export function LessonPlaceholderPage() {
  // SCRUM-64 reads the lesson id with useParams and loads the lesson.
  return (
    <div className="flex flex-col gap-4">
      <Link
        to="/"
        className="inline-flex w-fit items-center gap-1 rounded-sm text-sm font-medium text-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
      >
        <ChevronLeft className="size-4" aria-hidden />
        All content
      </Link>

      <h1 className="text-2xl font-bold text-ink">Lesson</h1>

      <Placeholder story="SCRUM-64" title="Lesson editor">
        Edit the lesson&rsquo;s title, topic, text and quiz question here. Published lessons are
        edited and withdrawn as in SCRUM-52.
      </Placeholder>
    </div>
  );
}
