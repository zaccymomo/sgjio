import { cn } from "@sgjio/ui";
import { Sparkles } from "lucide-react";
import { Link } from "react-router-dom";

import { MadeWithAi } from "./MadeWithAi";

/**
 * A way into "Generate a lesson" from outside the Practice tab: Home when every lesson is
 * done, and each topic page (docs/ai-lessons-plan.md). The same look as Practice's card.
 * `topicId` opens the form with that topic chosen.
 */
export function GeneratePrompt({
  title,
  text,
  topicId,
}: {
  title: string;
  text: string;
  topicId?: string;
}) {
  const to = topicId
    ? `/practice/generate?topic=${encodeURIComponent(topicId)}`
    : "/practice/generate";
  return (
    <section className="flex flex-col gap-3 rounded-lg border border-brand/30 bg-brand-soft/40 p-3.5">
      <div className="flex items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-brand text-white">
          <Sparkles className="size-5" aria-hidden />
        </span>
        <div className="flex min-w-0 flex-col gap-0.5">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold text-ink">{title}</h2>
            <MadeWithAi />
          </div>
          <p className="text-caption text-muted">{text}</p>
        </div>
      </div>
      <Link
        to={to}
        className={cn(
          "flex h-11 items-center justify-center rounded-sm bg-brand px-3 text-sm font-semibold text-white hover:bg-brand/90",
          "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
        )}
      >
        Generate a lesson
      </Link>
    </section>
  );
}
