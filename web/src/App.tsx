import { AppShell, AuthProvider, RequireAuth, type NavItem } from "@sgjio/ui";
import {
  Award,
  BookOpen,
  CalendarDays,
  CircleCheck,
  Download,
  Heart,
  History,
  Home,
  Lightbulb,
  MessageSquare,
  Settings,
  Store,
  Users,
} from "lucide-react";
import { BrowserRouter, Outlet, Route, Routes } from "react-router-dom";

import { ComingSoonPage } from "./pages/ComingSoonPage";
import { ChangePasswordPage, DeleteAccountPage } from "./pages/AccountSecurityPages";
import { AptitudeIntroPage, AptitudeQuizPage, AptitudeResultsPage } from "./pages/AptitudePages";
import { ForgotPasswordPage, ResetPasswordPage } from "./pages/PasswordPages";
import { RequireIntro } from "./components/RequireIntro";
import { HomePage } from "./pages/HomePage";
import { IntroPage } from "./pages/IntroPage";
import { LessonPage } from "./pages/LessonPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { EditProfilePage, ProfileSetupPage } from "./pages/ProfileSetupPage";
import { RegisterPage } from "./pages/RegisterPage";
import { PrivacyPage } from "./pages/PrivacyPage";
import { ReviewPage } from "./pages/ReviewPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SignInPage } from "./pages/SignInPage";
import { TopicPage } from "./pages/TopicPage";

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
          <Route path="/privacy" element={<PrivacyPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />

          {/* Signed in only: anyone else is sent to /sign-in?next=... */}
          <Route element={<RequireAuth />}>
            {/* Shown on first sign-in, and from Settings on request (SCRUM-94) */}
            <Route path="intro" element={<IntroPage />} />
            {/* Everything else waits until the introduction is finished or skipped */}
            <Route element={<RequireIntro />}>
              {/* A lesson fills the screen, without the app's bars (SCRUM-15) */}
              <Route path="lessons/:lessonId" element={<LessonPage />} />
              <Route element={<SignedInLayout />}>
                <Route index element={<HomePage />} />
                {/* Where the introduction leads a new account (SCRUM-94 AC1, SCRUM-61 AC8) */}
                <Route path="profile-setup" element={<ProfileSetupPage />} />
                <Route path="aptitude" element={<AptitudeIntroPage />} />
                <Route path="aptitude/quiz" element={<AptitudeQuizPage />} />
                <Route path="aptitude/results" element={<AptitudeResultsPage />} />
                {/* A progress circle leads here (SCRUM-43 AC9) */}
                <Route path="topics/:topicId" element={<TopicPage />} />
                {/* "Review mistakes" on the landing page leads here (SCRUM-44 AC1) */}
                <Route path="review" element={<ReviewPage />} />
                <Route
                  path="practice"
                  element={
                    <ComingSoonPage
                      title="AI Scenario Practice"
                      icon={MessageSquare}
                      summary="Practise real conversations with an AI partner, then see how it went."
                      features={[
                        {
                          icon: Store,
                          text: "Order at a hawker stall, chat with a neighbour or reply to your manager",
                        },
                        {
                          icon: Lightbulb,
                          text: "Get feedback on what went well and what a local might say instead",
                        },
                        { icon: BookOpen, text: "Practise the topics from your lessons" },
                      ]}
                    />
                  }
                />
                <Route
                  path="buddies"
                  element={
                    <ComingSoonPage
                      title="Buddy Matching"
                      icon={Users}
                      summary="Get matched with someone who can show you everyday Singapore."
                      features={[
                        {
                          icon: Heart,
                          text: "Be matched on shared interests, languages and neighbourhood",
                        },
                        {
                          icon: CalendarDays,
                          text: "Arrange sessions to try everyday situations together",
                        },
                        { icon: CircleCheck, text: "Keep a record of the sessions you've done" },
                      ]}
                    />
                  }
                />
                <Route
                  path="portfolio"
                  element={
                    <ComingSoonPage
                      title="Integration Portfolio"
                      icon={BookOpen}
                      summary="Keep a record of your lessons, practice and buddy sessions in one place."
                      features={[
                        { icon: History, text: "See everything you've done, newest first" },
                        { icon: Award, text: "Reach new tiers as your record grows" },
                        { icon: Download, text: "Download a copy to keep" },
                      ]}
                    />
                  }
                />
                <Route path="settings" element={<SettingsPage />} />
                <Route path="settings/change-password" element={<ChangePasswordPage />} />
                <Route path="settings/delete-account" element={<DeleteAccountPage />} />
                {/* The one profile editor, reached from Settings (SCRUM-14 AC4, SCRUM-41 AC5) */}
                <Route path="settings/profile" element={<EditProfilePage />} />
              </Route>
            </Route>
          </Route>

          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
