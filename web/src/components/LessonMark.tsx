import { Check, FastForward } from "lucide-react";

/**
 * The mark beside a lesson in a list: a filled tick once the user has completed it, a
 * dashed ring with a skip-ahead icon when the aptitude quiz exempted it instead (SCRUM-100),
 * and an empty ring otherwise. Shape as well as colour tells them apart.
 */
export function LessonMark({
  completed,
  exempted,
  small = false,
}: {
  completed: boolean;
  exempted: boolean;
  /** A size smaller, for tight lists such as the aptitude results. */
  small?: boolean;
}) {
  const box = small ? "size-5" : "size-6";
  if (completed) {
    return (
      <span
        className={`flex ${box} shrink-0 items-center justify-center rounded-full bg-brand text-white`}
      >
        <Check className={small ? "size-3" : "size-4"} strokeWidth={3} aria-hidden />
      </span>
    );
  }
  if (exempted) {
    return (
      <span
        className={`flex ${box} shrink-0 items-center justify-center rounded-full border-2 border-dashed border-brand bg-brand-soft text-brand`}
      >
        <FastForward className={small ? "size-2.5" : "size-3"} strokeWidth={2.5} aria-hidden />
      </span>
    );
  }
  return <span className={`${box} shrink-0 rounded-full border-2 border-line`} aria-hidden />;
}
