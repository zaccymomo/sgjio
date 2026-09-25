import { AuthCard, Placeholder } from "@sgjio/ui";
import { Link } from "react-router-dom";

export function RegisterPage() {
  return (
    <AuthCard
      title="Create an account"
      footer={
        <>
          Already have an account?{" "}
          <Link to="/sign-in" className="font-semibold text-brand hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <Placeholder story="SCRUM-61" title="Registration form">
        Name, email, password with confirmation, and Newcomer or Singaporean. Use TextField and
        PasswordField from @sgjio/ui, and the password rules in api/app/security.py.
      </Placeholder>
    </AuthCard>
  );
}
