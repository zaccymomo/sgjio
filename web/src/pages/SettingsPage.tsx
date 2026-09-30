import { Alert, Button, ErrorState, Spinner, formatDate, useAuth, type UserType } from "@sgjio/ui";
import { useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

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
  const profileSaved = (useLocation().state as { profileSaved?: boolean } | null)?.profileSaved;

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

      {/* AC1-AC2 */}
      {user && (
        <Section title="Account">
          <Detail label="Name">{user.name}</Detail>
          <Detail label="Email">{user.email}</Detail>
          <Detail label="User type">
            {user.user_type ? (
              <>
                {USER_TYPE_LABELS[user.user_type]}{" "}
                <span className="text-muted">(self-reported)</span>
              </>
            ) : (
              "Not set"
            )}
          </Detail>
          <Detail label="Joined">{formatDate(new Date(user.created_at))}</Detail>
        </Section>
      )}

      {/* AC3, AC5 */}
      <ProfileSection />

      <div className="flex flex-col items-start gap-2">
        {signOutError && <Alert tone="error">{signOutError}</Alert>}
        <Button variant="secondary" onClick={handleSignOut} loading={signingOut}>
          Sign out
        </Button>
      </div>
    </div>
  );
}

function ProfileSection() {
  const { state, reload } = useProfile();
  const editLink = (label: string) => (
    <Link to="/settings/profile" className="text-sm font-semibold text-brand hover:underline">
      {label}
    </Link>
  );

  if (state.status === "loading") {
    return (
      <Section title="Profile">
        <div className="flex justify-center py-6 text-brand">
          <Spinner className="size-5" label="Loading your profile" />
        </div>
      </Section>
    );
  }
  if (state.status === "error") {
    return (
      <Section title="Profile">
        <ErrorState message={state.message} onRetry={reload} />
      </Section>
    );
  }

  const profile: Profile = state.profile;
  if (!isProfileComplete(profile)) {
    return (
      <Section title="Profile" action={editLink("Set up")}>
        <p className="text-sm text-muted">
          Add your interests, languages and neighbourhood so lessons and buddies suit you.
        </p>
      </Section>
    );
  }

  return (
    <Section title="Profile" action={editLink("Edit")}>
      <Detail label="Interests">{profile.interests.join(", ")}</Detail>
      <Detail label="Languages">{profile.languages.join(", ")}</Detail>
      <Detail label="Neighbourhood">{profile.neighbourhood}</Detail>
    </Section>
  );
}

function Section({
  title,
  action,
  children,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-line bg-white p-4">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h2 className="text-caption font-semibold tracking-wide text-muted uppercase">{title}</h2>
        {action}
      </div>
      <dl className="flex flex-col gap-3">{children}</dl>
    </section>
  );
}

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:gap-4">
      <dt className="text-xs font-semibold text-muted sm:w-32 sm:shrink-0 sm:pt-0.5">{label}</dt>
      <dd className="text-sm text-ink">{children}</dd>
    </div>
  );
}
