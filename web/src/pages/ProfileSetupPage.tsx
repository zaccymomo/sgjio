import { Button, ErrorState, Spinner, useAuth } from "@sgjio/ui";
import { ChevronLeft } from "lucide-react";
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
  const next = user?.user_type === "newcomer" ? "/aptitude" : "/";

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-[22px] font-bold text-ink">
          Welcome to SGJio{firstName ? `, ${firstName}` : ""}
        </h1>
        <p className="mt-1 text-sm text-muted">
          Your account is ready. Three quick questions help us suggest lessons and buddies that suit
          you. You can change your answers any time in Settings.
        </p>
      </div>

      <LoadedProfileForm
        showProgress
        submitLabel="Continue"
        onSaved={() => navigate(next, { replace: true })}
        secondaryAction={
          <Button type="button" variant="ghost" onClick={() => navigate(next, { replace: true })}>
            Skip for now
          </Button>
        }
      />
    </div>
  );
}

/** Editing from the Profile tab (SCRUM-14 AC4, SCRUM-41 AC5; moved there in SCRUM-100). */
export function EditProfilePage() {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col gap-4">
      <div>
        <Link
          to="/profile"
          className="mb-2 inline-flex items-center gap-1 text-sm font-medium text-muted hover:text-ink"
        >
          <ChevronLeft className="size-4" aria-hidden />
          Profile
        </Link>
        <h1 className="text-[22px] font-bold text-ink">Edit your profile</h1>
        <p className="mt-1 text-sm text-muted">
          Changes are used for your next lesson suggestions and buddy matches.
        </p>
      </div>

      <LoadedProfileForm
        submitLabel="Save changes"
        onSaved={() => navigate("/profile", { state: { profileSaved: true } })}
        secondaryAction={
          <Link
            to="/profile"
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
