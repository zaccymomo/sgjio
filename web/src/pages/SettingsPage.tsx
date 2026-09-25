import { Button, Placeholder, useAuth } from "@sgjio/ui";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

/** Settings. Account details belong to SCRUM-41; sign-out to SCRUM-59. */
export function SettingsPage() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const [signingOut, setSigningOut] = useState(false);

  async function handleSignOut() {
    setSigningOut(true);
    try {
      await signOut();
      navigate("/sign-in", { replace: true });
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-[22px] font-bold text-ink">Settings</h1>

      <Placeholder story="SCRUM-41" title="Account and profile details">
        Signed in as <span className="font-medium text-ink">{user?.email}</span>. The full details
        page (name, user type, date joined, preferences) is built in SCRUM-41.
      </Placeholder>

      <div>
        <Button variant="secondary" onClick={handleSignOut} loading={signingOut}>
          Sign out
        </Button>
      </div>
    </div>
  );
}
