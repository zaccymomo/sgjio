import {
  AdminLayout,
  AuthProvider,
  Button,
  FullPageSpinner,
  RequireAuth,
  Spinner,
  useAuth,
} from "@sgjio/ui";
import { lazy, Suspense, useState } from "react";
import {
  Navigate,
  Outlet,
  Route,
  RouterProvider,
  createBrowserRouter,
  createRoutesFromElements,
  useMatch,
  useNavigate,
} from "react-router-dom";

import { ContentPage } from "./pages/ContentPage";
import { ForgotPasswordPage, ResetPasswordPage } from "./pages/PasswordPages";
import { SignInPage } from "./pages/SignInPage";

// Pages with the lesson deck load it only when opened, so the rest of the portal stays light.
const LessonEditorPage = lazy(() =>
  import("./pages/LessonEditorPage").then((module) => ({ default: module.LessonEditorPage })),
);
const LessonPreviewPage = lazy(() =>
  import("./pages/LessonPreviewPage").then((module) => ({ default: module.LessonPreviewPage })),
);

function SignedInLayout() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  // The lesson editor works in three panes, side by side.
  const wide = useMatch("/lessons/:id") !== null;
  const [signingOut, setSigningOut] = useState(false);

  async function handleSignOut() {
    setSigningOut(true);
    try {
      await signOut();
      navigate("/sign-in", { replace: true });
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <AdminLayout
      wide={wide}
      actions={
        <>
          <span className="hidden text-xs text-muted sm:inline">{user?.email}</span>
          <Button variant="secondary" size="sm" onClick={handleSignOut} loading={signingOut}>
            Sign out
          </Button>
        </>
      }
    >
      <Suspense
        fallback={
          <div className="flex justify-center py-16 text-brand">
            <Spinner className="size-6" label="Loading" />
          </div>
        }
      >
        <Outlet />
      </Suspense>
    </AdminLayout>
  );
}

/** Admin sessions are separate from main-app sessions (see api/app/auth). */
function Root() {
  return (
    <AuthProvider basePath="/api/admin/auth">
      <Outlet />
    </AuthProvider>
  );
}

// A data router (createBrowserRouter) rather than <BrowserRouter> as in the main app, because
// the lesson editor's unsaved-changes warning needs useBlocker, which only works with one.
// The routes are still written as JSX, so they read the same as the main app's.
const router = createBrowserRouter(
  createRoutesFromElements(
    <Route element={<Root />}>
      <Route path="/sign-in" element={<SignInPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />

      {/* Administrators only: anyone else is sent to /sign-in?next=... */}
      <Route element={<RequireAuth />}>
        {/* Full screen, without the portal's header (SCRUM-65). */}
        <Route
          path="/lessons/:id/preview"
          element={
            <Suspense fallback={<FullPageSpinner />}>
              <LessonPreviewPage />
            </Suspense>
          }
        />
        <Route element={<SignedInLayout />}>
          <Route index element={<ContentPage />} />
          {/* /lessons/new for a lesson not saved yet (SCRUM-64). */}
          <Route path="/lessons/:id" element={<LessonEditorPage />} />
          {/* Topics used to have their own page; they now live on the content page. */}
          <Route path="/topics" element={<Navigate to="/" replace />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Route>,
  ),
);

export function App() {
  return <RouterProvider router={router} />;
}
