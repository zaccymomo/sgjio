import { AuthCard, Placeholder } from "@sgjio/ui";
import { Link } from "react-router-dom";

const backToSignIn = (
  <Link to="/sign-in" className="font-semibold text-brand hover:underline">
    Back to sign in
  </Link>
);

export function ForgotPasswordPage() {
  return (
    <AuthCard title="Forgot your password?" badge="Admin" footer={backToSignIn}>
      <Placeholder story="SCRUM-69" title="Request a reset link">
        Call <code>request_password_reset</code> with the admin scope. It only emails administrator
        accounts.
      </Placeholder>
    </AuthCard>
  );
}

/** Where the emailed admin reset link lands: /reset-password?token=... */
export function ResetPasswordPage() {
  return (
    <AuthCard title="Choose a new password" badge="Admin" footer={backToSignIn}>
      <Placeholder story="SCRUM-69" title="Set a new password">
        Same flow as SCRUM-63, using the admin scope.
      </Placeholder>
    </AuthCard>
  );
}
