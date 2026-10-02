// Shared UI for the SGJio main app and admin portal (SCRUM-75).
// Import styles once per app with:  @import "@sgjio/ui/theme.css";

export { AdminLayout } from "./components/AdminLayout";
export { Alert } from "./components/Alert";
export { AppShell, type NavItem } from "./components/AppShell";
export { AuthCard } from "./components/AuthCard";
export { Button, type ButtonProps } from "./components/Button";
export { Dialog } from "./components/Dialog";
export { ErrorState } from "./components/ErrorState";
export { Logo } from "./components/Logo";
export { PasswordField } from "./components/PasswordField";
export { PasswordRules } from "./components/PasswordRules";
export { Placeholder } from "./components/Placeholder";
export { ForgotPasswordCard, ResetPasswordCard } from "./components/PasswordResetCards";
export { ProgressRing } from "./components/ProgressRing";
export { SignInForm } from "./components/SignInForm";
export { FullPageSpinner, Spinner } from "./components/Spinner";
export { TextField, type TextFieldProps } from "./components/TextField";

export { ApiError, apiFetch } from "./lib/api";
export { AuthProvider, RequireAuth } from "./lib/auth";
export {
  safeNextPath,
  useAuth,
  type AuthStatus,
  type RegisterInput,
  type ResetPasswordInput,
  type User,
  type UserType,
} from "./lib/auth-context";
export { cn } from "./lib/cn";
export { formatDate, formatTime } from "./lib/format";
export {
  looksLikeEmail,
  passwordRuleFailures,
  PASSWORD_HINT,
  PASSWORD_MAX_LENGTH,
  PASSWORD_MIN_LENGTH,
  PASSWORD_RULES,
} from "./lib/validation";
