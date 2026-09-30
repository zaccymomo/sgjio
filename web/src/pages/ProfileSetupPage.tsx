import { Button, ErrorState, Spinner, useAuth } from "@sgjio/ui";
import { Link, useNavigate } from "react-router-dom";

import { ProfileForm } from "../components/ProfileForm";
import { useProfile } from "../lib/profile";

/**
 * Where a newly registered account lands (SCRUM-61 AC8): interests, languages and
 * neighbourhood (SCRUM-14 AC1-AC2).
 */
export function ProfileSetupPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const firstName = user?.name.trim().split(/\s+/)[0];

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-[22px] font-bold text-ink">
          Welcome to SGJio{firstName ? `, ${firstName}` : ""}
        </h1>
        <p className="mt-1 text-sm text-muted">
          Your account is ready. Tell us a little more so lessons and buddies suit you.
        </p>
      </div>

      <LoadedProfileForm
        submitLabel="Continue"
        onSaved={() => navigate("/", { replace: true })}
        secondaryAction={
          <Button type="button" variant="ghost" onClick={() => navigate("/", { replace: true })}>
            Skip for now
          </Button>
        }
      />
    </div>
  );
}

/** Editing from Settings (SCRUM-14 AC4, SCRUM-41 AC5). */
export function EditProfilePage() {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-[22px] font-bold text-ink">Edit your profile</h1>
        <p className="mt-1 text-sm text-muted">
          Changes are used for your next lesson suggestions and buddy matches.
        </p>
      </div>

      <LoadedProfileForm
        submitLabel="Save changes"
        onSaved={() => navigate("/settings", { state: { profileSaved: true } })}
        secondaryAction={
          <Link
            to="/settings"
            className="flex h-11 items-center justify-center rounded-sm px-4 text-sm font-semibold text-muted hover:bg-surface hover:text-ink"
          >
            Cancel
          </Link>
        }
      />
    </div>
  );
}

function LoadedProfileForm(props: Omit<Parameters<typeof ProfileForm>[0], "initial" | "options">) {
  const { state, reload } = useProfile();

  if (state.status === "loading") {
    return (
      <div className="flex justify-center py-16 text-brand">
        <Spinner className="size-6" label="Loading your profile" />
      </div>
    );
  }
  if (state.status === "error") return <ErrorState message={state.message} onRetry={reload} />;
  return <ProfileForm initial={state.profile} options={state.options} {...props} />;
}
