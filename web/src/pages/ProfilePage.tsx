import { ErrorState, Spinner, cn, formatDate, useAuth } from "@sgjio/ui";
import { ChevronRight, Settings } from "lucide-react";
import { Link } from "react-router-dom";

import { TopicRadar } from "../components/TopicRadar";
import { useProgress } from "../lib/progress";
import { Initials } from "./SettingsPage";

/**
 * The Profile tab (SCRUM-100), which took the place of the Settings tab: who you are, and
 * the level you have reached in each topic as a radar chart that grows as you complete
 * lessons, until every spoke is full. A Newcomer's aptitude test results are a link away
 * (or the test itself, if they skipped it). Settings opens from the gear at the top.
 */
export function ProfilePage() {
  const { user } = useAuth();
  const { state, reload } = useProgress();

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-[22px] font-bold text-ink">Profile</h1>
        <Link
          to="/settings"
          aria-label="Settings"
          title="Settings"
          className={cn(
            "flex size-9 items-center justify-center rounded-sm border border-line text-ink",
            "transition-colors hover:bg-surface",
            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
          )}
        >
          <Settings className="size-4" aria-hidden />
        </Link>
      </div>

      {user && (
        <section className="flex items-center gap-3 rounded-lg border border-line bg-white p-4 sm:p-5">
          <Initials name={user.name} />
          <div className="min-w-0">
            <p className="truncate text-base font-semibold text-ink">{user.name}</p>
            <p className="text-sm text-muted">
              {user.user_type === "singaporean" ? "Singaporean" : "Newcomer"} · Member since{" "}
              {formatDate(new Date(user.created_at))}
            </p>
          </div>
        </section>
      )}

      {state.status === "loading" && (
        <div className="flex justify-center py-16 text-brand">
          <Spinner className="size-6" label="Loading your levels" />
        </div>
      )}

      {state.status === "error" && <ErrorState message={state.message} onRetry={reload} />}

      {state.status === "ready" && (
        <section className="rounded-lg border border-line bg-surface p-3.5">
          <h2 className="text-caption font-semibold tracking-wide text-muted uppercase">
            Your level in each topic
          </h2>

          {state.progress.topics.length === 0 ? (
            <p className="mt-2 text-sm text-muted">
              Your levels appear here as soon as the first lesson is published.
            </p>
          ) : (
            <>
              <p className="mt-1 text-caption text-muted">
                A topic&apos;s level rises once you&apos;ve covered every lesson at that level and
                below. Cover all of a topic&apos;s lessons to fill its spoke.
              </p>
              <div className="mt-3 rounded-lg border border-line bg-white p-3">
                <TopicRadar
                  topics={state.progress.topics.map((topic) => ({
                    id: topic.id,
                    name: topic.name,
                    level: topic.level,
                  }))}
                />
                {/* The same figures in words, and the only view with fewer than three topics. */}
                <ul className="mt-3 divide-y divide-line rounded-lg border border-line">
                  {state.progress.topics.map((topic) => (
                    <li key={topic.id}>
                      <Link
                        to={`/topics/${topic.id}`}
                        className={cn(
                          "flex items-center justify-between gap-3 p-3 text-sm",
                          "transition-colors hover:bg-surface",
                          "focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand",
                        )}
                      >
                        <span className="font-medium text-ink">{topic.name}</span>
                        <span className="flex shrink-0 items-center gap-1.5">
                          <span className="font-semibold text-brand">
                            {topic.completed >= topic.available
                              ? "Complete"
                              : `Level ${topic.level}`}
                          </span>
                          <ChevronRight className="size-4 text-subtle" aria-hidden />
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            </>
          )}

          {user?.user_type === "newcomer" &&
            (state.progress.aptitude_taken ? (
              <Link
                to="/aptitude/results"
                className="mt-3 inline-flex items-center gap-0.5 text-sm font-semibold text-brand hover:underline"
              >
                See your aptitude test results
                <ChevronRight className="size-4" aria-hidden />
              </Link>
            ) : (
              <Link
                to="/aptitude"
                className="mt-3 inline-flex items-center gap-0.5 text-sm font-semibold text-brand hover:underline"
              >
                Take the aptitude test to find your starting point
                <ChevronRight className="size-4" aria-hidden />
              </Link>
            ))}
        </section>
      )}
    </div>
  );
}
