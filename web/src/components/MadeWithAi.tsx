import { cn } from "@sgjio/ui";
import { Sparkles } from "lucide-react";

/** The "Made with AI" tag on everything an AI wrote for the learner. */
export function MadeWithAi({
  label = "Made with AI",
  className,
}: {
  label?: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] leading-4 font-semibold text-indigo-700",
        className,
      )}
    >
      {label}
    </span>
  );
}

/** The icon of a generated lesson: sparkles on an indigo square. */
export function AiLessonIcon() {
  return (
    <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-indigo-50 text-indigo-600">
      <Sparkles className="size-5" aria-hidden />
    </span>
  );
}
