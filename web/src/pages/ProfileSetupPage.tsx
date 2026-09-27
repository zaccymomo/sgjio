import { Button, Placeholder, useAuth } from "@sgjio/ui";
import { useNavigate } from "react-router-dom";

/**
 * Where a newly registered account lands (SCRUM-61 AC8). The form that collects
 * interests, languages and neighbourhood is SCRUM-14.
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

      <Placeholder story="SCRUM-14" title="Profile setup">
        Interests, languages and neighbourhood are collected here, then shown in Settings
        (SCRUM-41).
      </Placeholder>

      <div>
        <Button variant="secondary" onClick={() => navigate("/")}>
          Skip for now
        </Button>
      </div>
    </div>
  );
}
