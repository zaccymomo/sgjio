import { Alert, AuthCard, SignInForm, safeNextPath, useAuth } from "@sgjio/ui";
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";

/**
 * Main-app sign-in. Working scaffold for SCRUM-62: the form and redirect are done, and
 * the story owner checks it against the full acceptance criteria.
 */
export function SignInPage() {
  const { status } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = safeNextPath(params.get("next"));
  // Set by the reset-password page after a new password is saved (SCRUM-63 AC5).
  const passwordReset = (useLocation().state as { passwordReset?: boolean } | null)?.passwordReset;

  // Already signed in: go straight to where they were heading.
  if (status === "signed-in") return <Navigate to={next} replace />;

  return (
    <AuthCard
      title="Sign in"
      subtitle="Welcome back. Pick up where you left off."
      footer={
        <>
          New to SGJio?{" "}
          <Link to="/register" className="font-semibold text-brand hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      {passwordReset && (
        <Alert tone="success" className="mb-4">
          Your password has been reset. Sign in with your new password.
        </Alert>
      )}
      <SignInForm
        forgotPasswordHref="/forgot-password"
        onSuccess={() => navigate(next, { replace: true })}
      />
    </AuthCard>
  );
}
