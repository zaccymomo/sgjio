import { AuthCard, SignInForm, safeNextPath, useAuth } from "@sgjio/ui";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";

/**
 * Admin sign-in. Working scaffold for SCRUM-68: the form, admin-only rule and redirect
 * are done, and the story owner checks it against the full acceptance criteria.
 */
export function SignInPage() {
  const { status } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = safeNextPath(params.get("next"));

  if (status === "signed-in") return <Navigate to={next} replace />;

  return (
    <AuthCard
      title="Sign in to the admin portal"
      subtitle="For content administrators."
      badge="Admin"
    >
      <SignInForm
        forgotPasswordHref="/forgot-password"
        onSuccess={() => navigate(next, { replace: true })}
      />
    </AuthCard>
  );
}
