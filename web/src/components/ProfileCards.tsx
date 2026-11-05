import { ErrorState, Spinner, formatDate, type User, type UserType } from "@sgjio/ui";
import { Heart, Languages, MapPin, Pencil, Sparkles } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { isProfileComplete, useProfile, type Profile } from "../lib/profile";

/**
 * The pieces of the Profile tab that used to sit on Settings (SCRUM-41), moved as they were
 * when Profile took over "about you" and Settings kept "your account" (SCRUM-100).
 */

const USER_TYPE_LABELS: Record<UserType, string> = {
  newcomer: "Newcomer",
  singaporean: "Singaporean",
};

/** Your name, user type and when you joined (SCRUM-41 AC1-AC2). */
export function AboutYouCard({ user }: { user: User }) {
  return (
    <Card>
      <div className="flex items-center gap-3">
        <Initials name={user.name} />
        <p className="min-w-0 truncate text-base font-semibold text-ink">{user.name}</p>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-line pt-4">
        <div>
          <dt className="text-caption text-muted">User type</dt>
          <dd className="mt-0.5 text-sm font-medium text-ink">
            {user.user_type ? USER_TYPE_LABELS[user.user_type] : "Not set"}
            {user.user_type && (
              <span className="block text-caption font-normal text-subtle">Self-reported</span>
            )}
          </dd>
        </div>
        <div>
          <dt className="text-caption text-muted">Member since</dt>
          <dd className="mt-0.5 text-sm font-medium text-ink">
            {formatDate(new Date(user.created_at))}
          </dd>
        </div>
      </dl>
    </Card>
  );
}

/** Interests, languages and neighbourhood, with Edit (SCRUM-41 AC3, AC5). */
export function ProfileCard() {
  const { state, reload } = useProfile();

  if (state.status === "loading") {
    return (
      <Card title="Your profile">
        <div className="flex justify-center py-6 text-brand">
          <Spinner className="size-5" label="Loading your profile" />
        </div>
      </Card>
    );
  }
  if (state.status === "error") {
    return (
      <Card title="Your profile">
        <ErrorState message={state.message} onRetry={reload} />
      </Card>
    );
  }

  const profile: Profile = state.profile;

  if (!isProfileComplete(profile)) {
    return (
      <section className="flex flex-col items-start gap-3 rounded-lg border border-dashed border-line bg-surface p-5">
        <div className="flex size-9 items-center justify-center rounded-full bg-brand-soft text-brand">
          <Sparkles className="size-4" aria-hidden />
        </div>
        <div>
          <h2 className="text-base font-semibold text-ink">Finish setting up your profile</h2>
          <p className="mt-0.5 text-sm text-muted">
            Add your interests, languages and neighbourhood so lessons and buddies suit you.
          </p>
        </div>
        <Link
          to="/settings/profile"
          className="inline-flex h-9 items-center rounded-sm bg-ink px-3 text-sm font-semibold text-white hover:bg-ink/90"
        >
          Set up profile
        </Link>
      </section>
    );
  }

  return (
    <Card
      title="Your profile"
      action={
        <Link
          to="/settings/profile"
          className="inline-flex h-8 items-center gap-1.5 rounded-sm border border-line px-3 text-xs font-semibold text-ink hover:bg-surface"
        >
          <Pencil className="size-3.5" aria-hidden />
          Edit
        </Link>
      }
    >
      <dl className="flex flex-col gap-4">
        <ProfileRow icon={Heart} label="Interests">
          <Chips values={profile.interests} />
        </ProfileRow>
        <ProfileRow icon={Languages} label="Languages">
          <Chips values={profile.languages} />
        </ProfileRow>
        <ProfileRow icon={MapPin} label="Neighbourhood">
          <span className="text-sm text-ink">{profile.neighbourhood}</span>
        </ProfileRow>
      </dl>
    </Card>
  );
}

export function Card({
  title,
  action,
  children,
}: {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-line bg-white p-4 sm:p-5">
      {(title || action) && (
        <div className="mb-4 flex items-center justify-between gap-3">
          {title && <h2 className="text-base font-semibold text-ink">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

function ProfileRow({
  icon: Icon,
  label,
  children,
}: {
  icon: typeof Heart;
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <dt className="flex items-center gap-1.5 text-caption font-medium text-muted">
        <Icon className="size-3.5" aria-hidden />
        {label}
      </dt>
      <dd>{children}</dd>
    </div>
  );
}

function Chips({ values }: { values: string[] }) {
  return (
    <ul className="flex flex-wrap gap-1.5">
      {values.map((value) => (
        <li
          key={value}
          className="rounded-full border border-line bg-surface px-2.5 py-1 text-xs font-medium text-ink"
        >
          {value}
        </li>
      ))}
    </ul>
  );
}

/** A circle with the first letters of the first and last names. */
export function Initials({ name }: { name: string }) {
  const parts = name.trim().split(/\s+/);
  const letters = (parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "");
  return (
    <div
      className="flex size-12 shrink-0 items-center justify-center rounded-full bg-brand-soft text-base font-bold text-brand"
      aria-hidden
    >
      {letters.toUpperCase()}
    </div>
  );
}
