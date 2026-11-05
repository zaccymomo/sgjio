import type { LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";

export type ComingSoonFeature = { icon: LucideIcon; text: string };

/**
 * A tab whose module is planned but not built yet (Practice, Buddies, Portfolio). It tells
 * the learner what the tab will do for them, in their words, and leads back to the lessons
 * that exist today. Nothing here may suggest the app helps a PR application.
 */
export function ComingSoonPage({
  title,
  icon: Icon,
  summary,
  features,
}: {
  title: string;
  icon: LucideIcon;
  summary: string;
  features: ComingSoonFeature[];
}) {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-[22px] font-bold text-ink">{title}</h1>

      <section className="flex flex-col items-center gap-3 rounded-lg border border-line bg-white px-4 py-6 text-center sm:px-5">
        <span className="flex size-14 items-center justify-center rounded-full bg-brand-soft text-brand">
          <Icon className="size-6" aria-hidden />
        </span>
        <span className="rounded-sm bg-brand-soft px-1.5 py-0.5 text-2xs font-semibold text-brand">
          Coming soon
        </span>
        <p className="max-w-sm text-sm text-muted">{summary}</p>
      </section>

      <section className="rounded-lg border border-line bg-white p-4 sm:p-5">
        <h2 className="mb-3 text-base font-semibold text-ink">What you&apos;ll be able to do</h2>
        <ul className="flex flex-col gap-3">
          {features.map(({ icon: FeatureIcon, text }) => (
            <li key={text} className="flex items-start gap-3">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-sm border border-line bg-surface text-ink">
                <FeatureIcon className="size-4" aria-hidden />
              </span>
              <span className="pt-1.5 text-sm text-ink">{text}</span>
            </li>
          ))}
        </ul>
      </section>

      <Link
        to="/"
        className="flex h-11 items-center justify-center rounded-sm border border-line bg-white px-4 text-sm font-semibold text-ink hover:bg-surface focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
      >
        Back to my lessons
      </Link>
    </div>
  );
}
