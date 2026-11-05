import { Alert, ErrorState, Spinner, cn, useAuth } from "@sgjio/ui";
import { Settings } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

import { AboutYouCard, ProfileCard } from "../components/ProfileCards";
import { TopicRadar } from "../components/TopicRadar";
import { useProgress } from "../lib/progress";

/**
 * The Profile tab (SCRUM-100), which took the place of the Settings tab. In order: who you
 * are (SCRUM-41 AC1-AC2), the level you have reached in each topic as a radar chart that
 * grows as you complete lessons until every spoke is full, and your interests, languages
 * and neighbourhood (SCRUM-41 AC3, AC5). Your account, the introduction, security and
 * sign-out are in Settings, which opens from the gear at the top.
 */
export function ProfilePage() {
  const { user } = useAuth();
  const { state, reload } = useProgress();
  // Set by the profile editor after a save.
  const profileSaved = (useLocation().state as { profileSaved?: boolean } | null)?.profileSaved;

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

      {profileSaved && <Alert tone="success">Your profile has been updated.</Alert>}

      {/* SCRUM-41 AC1-AC2, as it was on Settings */}
      {user && <AboutYouCard user={user} />}

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
                {/* The chart needs three topics to make a shape; with fewer, say it in words. */}
                {state.progress.topics.length < 3 && (
                  <ul className="flex flex-col gap-1 text-sm">
                    {state.progress.topics.map((topic) => (
                      <li key={topic.id} className="flex justify-between gap-3">
                        <span className="text-ink">{topic.name}</span>
                        <span className="font-semibold text-brand">Level {topic.level}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </>
          )}
        </section>
      )}

      <ProfileCard />
    </div>
  );
}
