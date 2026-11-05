import { useAuth } from "@sgjio/ui";
import { Navigate, Outlet } from "react-router-dom";

/**
 * Sends someone who hasn't finished or skipped the introduction to it, whichever way they
 * came in: registering, Google, password sign-in or a link (SCRUM-94 AC1, AC6). Nested
 * inside RequireAuth, so the user is always known here.
 */
export function RequireIntro() {
  const { user } = useAuth();
  if (user && user.role === "user" && user.intro_finished_at === null) {
    return <Navigate to="/intro" replace />;
  }
  return <Outlet />;
}
