import { Alert, Button, useAuth } from "@sgjio/ui";
import { ChevronLeft, LogOut } from "lucide-react";
import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { GoogleLogo } from "../components/GoogleSignIn";
import { Card } from "../components/ProfileCards";

/**
 * Settings, opened from the gear on the Profile tab: your account (email and how you sign
 * in), the introduction again (SCRUM-94), account security and sign-out (SCRUM-59). Your
 * name, user type and profile details are on the Profile tab (SCRUM-100).
 */
export function SettingsPage() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState<string | null>(null);
  // Set by the change-password page after a change.
  const pageState = useLocation().state as { passwordChanged?: boolean } | null;

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
      {/* Settings opens from the Profile tab (SCRUM-100), so it leads back there. */}
      <Link
        to="/profile"
        className="inline-flex w-fit items-center gap-1 rounded-sm text-sm font-medium text-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
      >
        <ChevronLeft className="size-4" aria-hidden />
        Profile
      </Link>
      <h1 className="text-[22px] font-bold text-ink">Settings</h1>

      {pageState?.passwordChanged && (
        <Alert tone="success">
          Your password has been changed. This browser is still signed in.
        </Alert>
      )}

      {/* SCRUM-41 AC1: the account's email, and how it signs in (SCRUM-92) */}
      {user && (
        <Card title="Account">
          <dl className="flex flex-col gap-3">
            <div>
              <dt className="text-caption text-muted">Email</dt>
              <dd className="mt-0.5 truncate text-sm font-medium text-ink">{user.email}</dd>
            </div>
            <div>
              <dt className="text-caption text-muted">Signing in</dt>
              <dd className="mt-0.5 flex items-center gap-2 text-sm font-medium text-ink">
                {user.google_linked && <GoogleLogo />}
                {user.google_linked
                  ? user.has_password
                    ? "With Google or your password"
                    : "With Google"
                  : "With your email and password"}
              </dd>
            </div>
          </dl>
        </Card>
      )}

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
