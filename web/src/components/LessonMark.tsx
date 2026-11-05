import { Check, FastForward } from "lucide-react";

/**
 * The mark beside a lesson in a list: a filled tick once the user has completed it, a
 * dashed ring with a skip-ahead icon when the aptitude quiz exempted it instead (SCRUM-100),
 * and an empty ring otherwise. Shape as well as colour tells them apart.
 */
export function LessonMark({ completed, exempted }: { completed: boolean; exempted: boolean }) {
  if (completed) {
    return (
      <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-brand text-white">
        <Check className="size-4" strokeWidth={3} aria-hidden />
      </span>
    );
  }
  if (exempted) {
    return (
      <span className="flex size-6 shrink-0 items-center justify-center rounded-full border-2 border-dashed border-brand bg-brand-soft text-brand">
        <FastForward className="size-3" strokeWidth={2.5} aria-hidden />
      </span>
    );
  }
  return <span className="size-6 shrink-0 rounded-full border-2 border-line" aria-hidden />;
}
