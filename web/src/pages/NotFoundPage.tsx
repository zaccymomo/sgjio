import { AuthCard } from "@sgjio/ui";
import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <AuthCard title="Page not found" subtitle="The page you were looking for doesn't exist.">
      <Link to="/" className="text-sm font-semibold text-brand hover:underline">
        Go to the home page
      </Link>
    </AuthCard>
  );
}
