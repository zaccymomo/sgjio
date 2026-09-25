import { Construction } from "lucide-react";
import type { ReactNode } from "react";

/**
 * Marks a page or section that a later story will build, naming the Jira key so it is
 * obvious who picks it up. Delete it when the real page lands.
 */
export function Placeholder({
  story,
  title,
  children,
}: {
  story: string;
  title: string;
  children?: ReactNode;
}) {
  return (
    <section className="rounded-md border border-dashed border-line bg-surface p-5">
      <div className="flex items-start gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-white text-subtle">
          <Construction className="size-4" aria-hidden />
        </div>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold text-ink">{title}</h2>
            <span className="rounded-sm bg-brand-soft px-1.5 py-0.5 text-2xs font-semibold text-brand">
              {story}
            </span>
          </div>
          {children && <div className="mt-1 text-sm text-muted">{children}</div>}
        </div>
      </div>
    </section>
  );
}
