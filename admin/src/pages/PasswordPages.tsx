import {
  Alert,
  ApiError,
  AuthCard,
  Button,
  CheckingLink,
  ForgotPasswordCard,
  LinkButton,
  NewPasswordForm,
  ResetPasswordCard,
  apiFetch,
  useAuth,
} from "@sgjio/ui";
import { Link2Off, Mail, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import type { Notice } from "../lib/content";

const INVITE_CHECK = "/api/admin/auth/invite/check";
const INVITE_ACCEPT = "/api/admin/auth/invite/accept";

const backToSignIn = (
  <Link to="/sign-in" className="font-semibold text-brand hover:underline">
    Back to sign in
  </Link>
);

/**
 * SCRUM-69 AC1-AC3, on the same card as the main app (SCRUM-63). An administrator still
 * waiting to set up their account is sent a new invite instead (SCRUM-81).
 */
export function ForgotPasswordPage() {
  return (
    <ForgotPasswordCard
      badge="Admin"
      subtitle="Enter your administrator email and we'll send you a link to choose a new password."
      footer={backToSignIn}
    />
  );
}

/** Where an emailed admin reset link lands: /reset-password?token=... (SCRUM-69 AC4-AC7). */
export function ResetPasswordPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();

  return (
    <ResetPasswordCard
      token={params.get("token")}
      badge="Admin"
      forgotPasswordHref="/forgot-password"
      footer={backToSignIn}
      // Say it worked, on the sign-in page (AC5).
      onSuccess={() => navigate("/sign-in", { replace: true, state: { passwordReset: true } })}
    />
  );
}

type Invite = { name: string; email: string; invited_by: string | null };

type InviteState =
  | { status: "checking" }
  | { status: "ready"; invite: Invite }
  | { status: "invalid" }
  | { status: "unreachable"; message: string };

/** What an invite link is, from the server. `null`: the check was cancelled. */
async function checkInvite(token: string, signal?: AbortSignal): Promise<InviteState | null> {
  try {
    const invite = await apiFetch<Invite>(INVITE_CHECK, {
      method: "POST",
      body: { token },
      signal,
    });
    return { status: "ready", invite };
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") return null;
    if (error instanceof ApiError && error.code === "invite_link_invalid") {
      return { status: "invalid" };
    }
    return {
      status: "unreachable",
      message:
        error instanceof ApiError ? error.message : "Something went wrong. Please try again.",
    };
  }
}

/**
 * Where an invite email lands: /set-password?token=... (SCRUM-81 AC2). Greets the person by
 * name, says who invited them and which email they will sign in with, and once they choose
 * a password, signs them straight in.
 */
export function SetPasswordPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get("token");
  const { refresh } = useAuth();
  const [state, setState] = useState<InviteState>(
    token ? { status: "checking" } : { status: "invalid" },
  );

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    void checkInvite(token, controller.signal).then((next) => next && setState(next));
    return () => controller.abort();
  }, [token]);

  if (state.status === "invalid") {
    return (
      <AuthCard
        title="This invite link no longer works"
        subtitle="Invite links work once, last a few days, and stop working when a newer invite is sent."
        icon={Link2Off}
        badge="Admin"
        footer={
          <>
            Already set up?{" "}
            <Link to="/sign-in" className="font-semibold text-brand hover:underline">
              Sign in
            </Link>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <LinkButton to="/forgot-password">Email me a new link</LinkButton>
          <p className="text-center text-xs text-muted">
            Or ask the administrator who invited you to send it again.
          </p>
        </div>
      </AuthCard>
    );
  }

  if (state.status === "unreachable") {
    return (
      <AuthCard title="Set up your account" icon={ShieldCheck} badge="Admin" footer={backToSignIn}>
        <div className="flex flex-col gap-4">
          <Alert tone="error">{state.message}</Alert>
          <Button
            fullWidth
            onClick={() => {
              setState({ status: "checking" });
              void checkInvite(token ?? "").then((next) => next && setState(next));
            }}
          >
            Try again
          </Button>
        </div>
      </AuthCard>
    );
  }

  if (state.status === "checking") {
    return (
      <AuthCard
        title="Set up your account"
        subtitle="Checking your invite…"
        icon={ShieldCheck}
        badge="Admin"
      >
        <CheckingLink />
      </AuthCard>
    );
  }

  const { invite } = state;
  const first = invite.name.split(/\s+/)[0];
  return (
    <AuthCard
      title={`Welcome, ${first}`}
      subtitle={
        <>
          {invite.invited_by ? (
            <strong className="font-semibold text-ink">{invite.invited_by}</strong>
          ) : (
            "Your team"
          )}{" "}
          invited you to the SGJio admin portal. Choose a password to finish setting up.
        </>
      }
      icon={ShieldCheck}
      badge="Admin"
    >
      <div className="flex flex-col gap-5">
        <div className="flex items-center gap-3 rounded-md bg-surface px-3 py-2.5">
          <Mail className="size-4 shrink-0 text-muted" aria-hidden />
          <div className="min-w-0">
            <p className="text-caption text-muted">You&rsquo;ll sign in with</p>
            <p className="truncate text-sm font-semibold text-ink">{invite.email}</p>
          </div>
        </div>
        <NewPasswordForm
          submitLabel="Set password and sign in"
          deadLinkCode="invite_link_invalid"
          onDeadLink={() => setState({ status: "invalid" })}
          onSubmit={async (password, confirmation) => {
            await apiFetch(INVITE_ACCEPT, {
              method: "POST",
              body: { token, password, password_confirmation: confirmation },
            });
            await refresh();
            const notice: Notice = {
              tone: "success",
              message: `Welcome to SGJio admin, ${first}. You're signed in.`,
            };
            navigate("/", { replace: true, state: { notice } });
          }}
        />
      </div>
    </AuthCard>
  );
}
