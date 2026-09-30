import { AuthCard, ForgotPasswordForm, ResetPasswordForm } from "@sgjio/ui";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

const backToSignIn = (
  <Link to="/sign-in" className="font-semibold text-brand hover:underline">
    Back to sign in
  </Link>
);

/** SCRUM-63 AC1-AC3: reached from "Forgot password?" on the sign-in page. */
export function ForgotPasswordPage() {
  return (
    <AuthCard title="Forgot your password?" footer={backToSignIn}>
      <ForgotPasswordForm />
    </AuthCard>
  );
}

/** Where the emailed reset link lands: /reset-password?token=... (SCRUM-63 AC4-AC6) */
export function ResetPasswordPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();

  return (
    <AuthCard title="Choose a new password" footer={backToSignIn}>
      <ResetPasswordForm
        token={params.get("token")}
        forgotPasswordHref="/forgot-password"
        // AC5: say it worked, on the sign-in page.
        onSuccess={() => navigate("/sign-in", { replace: true, state: { passwordReset: true } })}
      />
    </AuthCard>
  );
}
