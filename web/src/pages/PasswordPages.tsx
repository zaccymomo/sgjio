import { AuthCard, Placeholder } from "@sgjio/ui";
import { Link } from "react-router-dom";

const backToSignIn = (
  <Link to="/sign-in" className="font-semibold text-brand hover:underline">
    Back to sign in
  </Link>
);

export function ForgotPasswordPage() {
  return (
    <AuthCard title="Forgot your password?" footer={backToSignIn}>
      <Placeholder story="SCRUM-63" title="Request a reset link">
        Call <code>request_password_reset</code> in api/app/auth/reset.py. Emails are already set up
        (SCRUM-74).
      </Placeholder>
    </AuthCard>
  );
}

/** Where the emailed reset link lands: /reset-password?token=... */
export function ResetPasswordPage() {
  return (
    <AuthCard title="Choose a new password" footer={backToSignIn}>
      <Placeholder story="SCRUM-63" title="Set a new password">
        Check the link with <code>check_reset_token</code>, then save with{" "}
        <code>consume_reset_token</code> and <code>set_new_password</code>.
      </Placeholder>
    </AuthCard>
  );
}
