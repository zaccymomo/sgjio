import { Alert, Button, ErrorState, Spinner, formatDate, useAuth, type UserType } from "@sgjio/ui";
import { Heart, Languages, LogOut, MapPin, Pencil, Sparkles } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { GoogleLogo } from "../components/GoogleSignIn";
import { isProfileComplete, useProfile, type Profile } from "../lib/profile";

const USER_TYPE_LABELS: Record<UserType, string> = {
  newcomer: "Newcomer",
  singaporean: "Singaporean",
};

/**
 * Settings: account and profile details (SCRUM-41, view only) and sign-out (SCRUM-59).
 * Profile changes happen in the one editor at /settings/profile (SCRUM-14).
 */
export function SettingsPage() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState<string | null>(null);
  // Set by the profile editor after a save.
  const pageState = useLocation().state as {
    profileSaved?: boolean;
    passwordChanged?: boolean;
  } | null;
  const profileSaved = pageState?.profileSaved;

  async function handleSignOut() {
    setSigningOut(true);
    setSignOutError(null);
    try {
      await signOut();
      navigate("/sign-in", { replace: true });
    } catch {
      setSignOutError("We couldn't sign you out. Check your connection and try again.");
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-[22px] font-bold text-ink">Settings</h1>

      {profileSaved && <Alert tone="success">Your profile has been updated.</Alert>}
      {pageState?.passwordChanged && (
        <Alert tone="success">
          Your password has been changed. This browser is still signed in.
        </Alert>
      )}

      {/* SCRUM-41 AC1-AC2 */}
      {user && (
        <Card>
          <div className="flex items-center gap-3">
            <Initials name={user.name} />
            <div className="min-w-0">
              <p className="truncate text-base font-semibold text-ink">{user.name}</p>
              <p className="truncate text-sm text-muted">{user.email}</p>
            </div>
          </div>
          {/* SCRUM-92 */}
          {user.google_linked && (
            <p className="mt-3 flex items-center gap-2 text-sm text-ink">
              <GoogleLogo />
              {user.has_password
                ? "Signed in with Google or your password"
                : "Signed in with Google"}
            </p>
          )}
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
      )}

      {/* SCRUM-41 AC3, AC5 */}
      <ProfileCard />

      {/* SCRUM-94: the introduction is only shown once, but can be seen again from here */}
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-ink">About SGJio</p>
            <p className="text-sm text-muted">A short walkthrough of what the app does for you.</p>
          </div>
          <Link
            to="/intro?replay=1"
            className="inline-flex h-8 items-center rounded-sm border border-line px-3 text-xs font-semibold text-ink hover:bg-surface"
          >
            View the introduction again
          </Link>
        </div>
      </Card>

      {user?.role !== "admin" && (
        <Card>
          <div className="space-y-3">
            <p className="text-sm font-semibold text-ink">Account security</p>
            <p className="text-sm text-muted">
              {user?.has_password
                ? "Update your password or remove your account and data."
                : "You sign in with Google, so there's no password to change. You can remove your account and data."}
            </p>
            <div className="flex flex-wrap gap-4 text-sm">
              {user?.has_password && (
                <Link to="/settings/change-password" className="font-semibold text-brand underline">
                  Change password
                </Link>
              )}
              <Link to="/settings/delete-account" className="font-semibold text-danger underline">
                Delete account
              </Link>
            </div>
          </div>
        </Card>
      )}

      {/* SCRUM-59 */}
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-ink">Sign out</p>
            <p className="text-sm text-muted">Signs you out of SGJio in this browser.</p>
          </div>
          <Button variant="secondary" size="sm" onClick={handleSignOut} loading={signingOut}>
            <LogOut className="size-3.5" aria-hidden />
            Sign out
          </Button>
        </div>
        {signOutError && (
          <Alert tone="error" className="mt-3">
            {signOutError}
          </Alert>
        )}
      </Card>
    </div>
  );
}

function ProfileCard() {
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

function Card({
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
function Initials({ name }: { name: string }) {
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
