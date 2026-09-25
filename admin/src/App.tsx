import { AdminLayout, AuthProvider, Button, RequireAuth, useAuth } from "@sgjio/ui";
import { useState } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes, useNavigate } from "react-router-dom";

import { LessonsPage } from "./pages/LessonsPage";
import { ForgotPasswordPage, ResetPasswordPage } from "./pages/PasswordPages";
import { SignInPage } from "./pages/SignInPage";

function SignedInLayout() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
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
      actions={
        <>
          <span className="hidden text-xs text-muted sm:inline">{user?.email}</span>
          <Button variant="secondary" size="sm" onClick={handleSignOut} loading={signingOut}>
            Sign out
          </Button>
        </>
      }
    >
      <Outlet />
    </AdminLayout>
  );
}

export function App() {
  return (
    <BrowserRouter>
      {/* Admin sessions are separate from main-app sessions (see api/app/auth). */}
      <AuthProvider basePath="/api/admin/auth">
        <Routes>
          <Route path="/sign-in" element={<SignInPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />

          {/* Administrators only: anyone else is sent to /sign-in?next=... */}
          <Route element={<RequireAuth />}>
            <Route element={<SignedInLayout />}>
              <Route index element={<LessonsPage />} />
            </Route>
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
