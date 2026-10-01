import { Button, Placeholder } from "@sgjio/ui";
import { Plus } from "lucide-react";

/** Admin landing page. The lesson list itself is SCRUM-66. */
export function LessonsPage() {
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-ink">Lessons</h1>
        <Button disabled>
          <Plus className="size-4" aria-hidden />
          New lesson
        </Button>
      </div>

      <Placeholder story="SCRUM-66" title="Lesson list">
        Every lesson with its title, topic, status (Draft, Published or Withdrawn) and last update,
        newest first, with filters and search.
      </Placeholder>
      <Placeholder story="SCRUM-64" title="Lesson editor">
        Opened by "New lesson" and by selecting a draft.
      </Placeholder>
    </div>
  );
}
