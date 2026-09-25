import { AppShell, AuthProvider, RequireAuth, type NavItem } from "@sgjio/ui";
import { BookOpen, Home, MessageSquare, Settings, Users } from "lucide-react";
import { BrowserRouter, Outlet, Route, Routes } from "react-router-dom";

import { ComingSoonPage } from "./pages/ComingSoonPage";
import { ForgotPasswordPage, ResetPasswordPage } from "./pages/PasswordPages";
import { HomePage } from "./pages/HomePage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { RegisterPage } from "./pages/RegisterPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SignInPage } from "./pages/SignInPage";

// The five tabs from the Figma bottom bar.
const NAV: NavItem[] = [
  { to: "/", label: "Home", icon: Home },
  { to: "/practice", label: "Practice", icon: MessageSquare },
  { to: "/buddies", label: "Buddies", icon: Users },
  { to: "/portfolio", label: "Portfolio", icon: BookOpen },
  { to: "/settings", label: "Settings", icon: Settings },
];

function SignedInLayout() {
  return (
    <AppShell nav={NAV}>
      <Outlet />
    </AppShell>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider basePath="/api/auth">
        <Routes>
          {/* Open to everyone */}
          <Route path="/sign-in" element={<SignInPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />

          {/* Signed in only: anyone else is sent to /sign-in?next=... */}
          <Route element={<RequireAuth />}>
            <Route element={<SignedInLayout />}>
              <Route index element={<HomePage />} />
              <Route
                path="practice"
                element={<ComingSoonPage title="AI scenario practice" module="Module 4" />}
              />
              <Route
                path="buddies"
                element={<ComingSoonPage title="Buddy matching" module="Module 2" />}
              />
              <Route
                path="portfolio"
                element={<ComingSoonPage title="Integration portfolio" module="Module 3" />}
              />
              <Route path="settings" element={<SettingsPage />} />
            </Route>
          </Route>

          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
