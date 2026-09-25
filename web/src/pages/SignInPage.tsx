import { AuthCard, SignInForm, safeNextPath, useAuth } from "@sgjio/ui";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";

/**
 * Main-app sign-in. Working scaffold for SCRUM-62: the form and redirect are done, and
 * the story owner checks it against the full acceptance criteria.
 */
export function SignInPage() {
  const { status } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = safeNextPath(params.get("next"));

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
      <SignInForm
        forgotPasswordHref="/forgot-password"
        onSuccess={() => navigate(next, { replace: true })}
      />
    </AuthCard>
  );
}
