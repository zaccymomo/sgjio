import { ErrorState, Spinner, apiFetch, cn } from "@sgjio/ui";
import { ChevronRight, MessageSquare, Sparkles } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { AiLessonIcon, MadeWithAi } from "../components/MadeWithAi";
import {
  WAITING,
  dayLabel,
  errorMessage,
  plural,
  type GenerateOptions,
  type GeneratedListItem,
} from "../lib/generated";

type State =
  | { status: "loading" }
  | { status: "ready"; options: GenerateOptions; lessons: GeneratedListItem[] }
  | { status: "error"; message: string };

const linkFocus =
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand";

/**
 * The Practice tab (docs/ai-lessons-plan.md, step 1): generate a lesson, the lessons
 * generated so far, and AI Scenario Practice, still to come.
 */
export function PracticePage() {
  const [state, setState] = useState<State>({ status: "loading" });

  const load = useCallback(async (signal?: AbortSignal): Promise<State | null> => {
    try {
      const [options, lessons] = await Promise.all([
        apiFetch<GenerateOptions>("/api/generate/options", { signal }),
        apiFetch<GeneratedListItem[]>("/api/generated", { signal }),
      ]);
      return { status: "ready", options, lessons };
    } catch (error) {
      if (signal?.aborted) return null;
      return {
        status: "error",
        message: errorMessage(error, "We couldn't load Practice. Check your connection."),
      };
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal).then((next) => next && setState(next));
    return () => controller.abort();
  }, [load]);

  async function reload() {
    setState({ status: "loading" });
    const next = await load();
    if (next) setState(next);
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-[22px] font-bold text-ink">Practice</h1>

      {state.status === "loading" && (
        <div className="flex justify-center py-16 text-brand">
          <Spinner className="size-6" label="Loading Practice" />
        </div>
      )}

      {state.status === "error" && (
        <ErrorState message={state.message} onRetry={() => void reload()} />
      )}

      {state.status === "ready" && (
        <>
          <GenerateCard options={state.options} />
          <GeneratedList lessons={state.lessons} />
        </>
      )}

      <section className="flex items-start gap-3 rounded-lg border border-line bg-white p-4">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-brand-soft text-brand">
          <MessageSquare className="size-5" aria-hidden />
        </span>
        <div className="flex min-w-0 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold text-ink">AI Scenario Practice</h2>
            <span className="rounded-sm bg-brand-soft px-1.5 py-0.5 text-2xs font-semibold text-brand">
              Coming soon
            </span>
          </div>
          <p className="text-caption text-muted">
            Practise real conversations with an AI partner, then see how it went.
          </p>
        </div>
      </section>
    </div>
  );
}

function GenerateCard({ options }: { options: GenerateOptions }) {
  const { left_today, mistakes_total } = options;
  return (
    <section className="flex flex-col gap-3 rounded-lg border border-brand/30 bg-brand-soft/40 p-4">
      <div className="flex items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-brand text-white">
          <Sparkles className="size-5" aria-hidden />
        </span>
        <div className="flex min-w-0 flex-col gap-0.5">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold text-ink">Generate a lesson</h2>
            <MadeWithAi />
          </div>
          <p className="text-caption text-muted">
            A short lesson tailored to you, based on your mistakes or a topic of your choice.
          </p>
        </div>
      </div>
      <div className="flex gap-2">
        <Link
          to="/practice/generate"
          className={cn(
            "flex h-11 flex-1 items-center justify-center rounded-sm bg-brand px-3 text-sm font-semibold text-white hover:bg-brand/90",
            linkFocus,
          )}
        >
          Generate
        </Link>
        {mistakes_total > 0 && (
          <Link
            to="/practice/generate?focus=mistakes"
            className={cn(
              "flex h-11 flex-1 items-center justify-center rounded-sm border border-line bg-white px-3 text-center text-sm font-semibold text-ink hover:bg-surface",
              linkFocus,
            )}
          >
            Practise {plural(mistakes_total, "mistake", "mistakes")}
          </Link>
        )}
      </div>
      <p className="text-caption text-muted">
        {left_today} remaining today. Generated lessons do not affect your progress.
      </p>
    </section>
  );
}

function GeneratedList({ lessons }: { lessons: GeneratedListItem[] }) {
  return (
    <section className="flex flex-col gap-2.5">
      <h2 className="text-caption font-semibold tracking-wide text-muted uppercase">
        Your generated lessons
      </h2>
      {lessons.length === 0 ? (
        <p className="text-sm text-muted">Lessons you generate will appear here.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {lessons.map((lesson) => {
            const waiting = WAITING.includes(lesson.status);
            return (
              <li key={lesson.id}>
                <Link
                  to={`/practice/generated/${lesson.id}`}
                  className={cn(
                    "flex items-center gap-3 rounded-lg border border-line bg-white px-3.5 py-3",
                    "transition-colors hover:border-brand/40 hover:bg-brand-soft/40",
                    linkFocus,
                  )}
                >
                  <AiLessonIcon />
                  <span className="flex min-w-0 flex-1 flex-col">
                    {waiting ? (
                      <span className="flex items-center gap-2 text-sm font-semibold text-ink">
                        Preparing your lesson…
                        <Spinner className="size-3.5 text-brand" label="Writing" />
                      </span>
                    ) : (
                      <span className="text-sm font-semibold text-ink">{lesson.title}</span>
                    )}
                    <span className="text-caption text-subtle">
                      {lesson.topic.name} · {dayLabel(lesson.created_at)}
                      {!waiting &&
                        (lesson.best
                          ? ` · Best score ${lesson.best.correct} / ${lesson.best.scored}`
                          : " · Not attempted yet")}
                    </span>
                  </span>
                  <ChevronRight className="size-4 shrink-0 text-subtle" aria-hidden />
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
