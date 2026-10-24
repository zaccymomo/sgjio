import { Alert, ApiError, Button, Dialog, TextField, looksLikeEmail } from "@sgjio/ui";
import { BookOpen, KeyRound, LogOut, Mail, MailX, RotateCcw, type LucideIcon } from "lucide-react";
import { useRef, useState, type FormEvent, type ReactNode } from "react";

import { emailDomain, inviteLifetime, type Admin } from "../../lib/admins";
import { Avatar } from "./Avatar";

type FieldErrors = { name?: string; email?: string };

/** A refusal that has a better next step than editing the form, e.g. "Resend invite". */
type Redirect = { message: string; label: string; run: () => Promise<void> };

/**
 * Invite an administrator (SCRUM-81 AC2). Checks the obvious on the spot, warns before
 * inviting someone outside the team's email domain, and turns the server's refusals into
 * next steps: a learner's email is shown on the field (AC3), while someone already invited
 * or removed is offered "Resend invite" or "Restore" instead.
 */
export function AddAdminDialog({
  open,
  domain,
  inviteHours,
  onClose,
  onInvite,
  onResend,
  onRestore,
}: {
  open: boolean;
  domain: string | null;
  inviteHours: number;
  onClose: () => void;
  /** Throws an ApiError if the server refuses. */
  onInvite: (name: string, email: string, allowOtherDomain: boolean) => Promise<void>;
  onResend: (adminId: string) => Promise<void>;
  onRestore: (adminId: string) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <Dialog
      open={open}
      title="Add an administrator"
      description="They can edit topics and lessons, and add or remove administrators, just like you."
      onClose={onClose}
      dismissible={!busy}
    >
      <AddAdminForm
        domain={domain}
        inviteHours={inviteHours}
        busy={busy}
        setBusy={setBusy}
        onCancel={onClose}
        onInvite={onInvite}
        onResend={onResend}
        onRestore={onRestore}
      />
    </Dialog>
  );
}

function AddAdminForm({
  domain,
  inviteHours,
  busy,
  setBusy,
  onCancel,
  onInvite,
  onResend,
  onRestore,
}: {
  domain: string | null;
  inviteHours: number;
  busy: boolean;
  setBusy: (busy: boolean) => void;
  onCancel: () => void;
  onInvite: (name: string, email: string, allowOtherDomain: boolean) => Promise<void>;
  onResend: (adminId: string) => Promise<void>;
  onRestore: (adminId: string) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string>();
  const [redirect, setRedirect] = useState<Redirect | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);

  const trimmed = email.trim();
  const otherDomain =
    domain && looksLikeEmail(trimmed) && emailDomain(trimmed) !== domain
      ? emailDomain(trimmed)
      : null;

  async function run(action: () => Promise<void>, fallback: string) {
    setBusy(true);
    try {
      await action();
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : fallback);
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(undefined);
    setRedirect(null);
    const errors: FieldErrors = {};
    if (!name.trim()) errors.name = "Enter their name.";
    if (!trimmed) errors.email = "Enter their email.";
    else if (!looksLikeEmail(trimmed))
      errors.email = "Enter an email address like name@example.com.";
    setFieldErrors(errors);
    if (errors.name) return nameRef.current?.focus();
    if (errors.email) return emailRef.current?.focus();

    setBusy(true);
    try {
      await onInvite(name.trim(), trimmed, otherDomain !== null);
    } catch (error) {
      if (!(error instanceof ApiError)) {
        setFormError("We couldn't send the invite. Please try again.");
      } else if (error.code === "validation_error") {
        setFieldErrors(error.fieldErrors);
      } else if (error.code === "already_invited" || error.code === "admin_removed") {
        const id = String(error.details.admin_id);
        setRedirect(
          error.code === "already_invited"
            ? { message: error.message, label: "Resend invite", run: () => onResend(id) }
            : { message: error.message, label: "Restore them", run: () => onRestore(id) },
        );
      } else if (error.field === "email") {
        setFieldErrors({ email: error.message });
        emailRef.current?.focus();
      } else {
        setFormError(error.message);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      {formError && <Alert tone="error">{formError}</Alert>}
      <TextField
        ref={nameRef}
        label="Name"
        autoComplete="off"
        maxLength={120}
        data-autofocus
        value={name}
        onChange={(event) => setName(event.target.value)}
        error={fieldErrors.name}
      />
      <div className="flex flex-col gap-2">
        <TextField
          ref={emailRef}
          label="Email"
          type="email"
          inputMode="email"
          autoComplete="off"
          placeholder={domain ? `name@${domain}` : "name@example.com"}
          maxLength={254}
          value={email}
          onChange={(event) => {
            setEmail(event.target.value);
            setRedirect(null);
            if (fieldErrors.email) setFieldErrors({ ...fieldErrors, email: undefined });
          }}
          error={fieldErrors.email}
        />
        {otherDomain && !fieldErrors.email && (
          <Alert tone="warning">
            <strong className="font-semibold">{otherDomain}</strong> isn&rsquo;t your team&rsquo;s
            domain ({domain}). Check this is the right person before you invite them.
          </Alert>
        )}
        {redirect && (
          <div className="flex flex-col gap-3 rounded-md border border-line bg-surface p-3 sm:flex-row sm:items-center">
            <p className="flex-1 text-sm text-ink">{redirect.message}</p>
            <Button
              size="sm"
              variant="secondary"
              loading={busy}
              onClick={() => void run(redirect.run, "That didn't work. Please try again.")}
            >
              {redirect.label}
            </Button>
          </div>
        )}
      </div>

      <p className="flex items-start gap-2 text-xs text-muted">
        <Mail className="mt-px size-3.5 shrink-0" aria-hidden />
        <span>
          We&rsquo;ll email them a link to choose a password. It works once and lasts{" "}
          {inviteLifetime(inviteHours)}.
        </span>
      </p>

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button variant="secondary" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
        <Button type="submit" loading={busy && !redirect}>
          {otherDomain ? "Invite anyway" : "Send invite"}
        </Button>
      </div>
    </form>
  );
}

/** One consequence in a confirmation, with its icon. */
function Consequence({ icon: Icon, children }: { icon: LucideIcon; children: ReactNode }) {
  return (
    <li className="flex items-start gap-3">
      <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-surface text-muted">
        <Icon className="size-3.5" aria-hidden />
      </span>
      <span>{children}</span>
    </li>
  );
}

/** Who a confirmation is about, so the right person is unmistakable. */
function PersonCard({ admin }: { admin: Admin }) {
  return (
    <div className="flex items-center gap-3 rounded-md border border-line p-3">
      <Avatar name={admin.name} seed={admin.email} />
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold text-ink">{admin.name}</p>
        <p className="truncate text-xs text-muted">{admin.email}</p>
      </div>
    </div>
  );
}

export type ConfirmState = { kind: "remove" | "restore"; admin: Admin };

/** Confirm removing an administrator or cancelling an invite (AC4), or restoring one. */
export function ConfirmAdminDialog({
  state,
  busy,
  error,
  onCancel,
  onConfirm,
}: {
  state: ConfirmState | null;
  busy: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const admin = state?.admin;
  const first = admin?.name.split(/\s+/)[0] ?? "";
  const invited = admin?.status === "invited";

  const restoring = state?.kind === "restore";
  const title = !admin
    ? ""
    : restoring
      ? `Restore ${admin.name}?`
      : invited
        ? `Cancel ${first}'s invite?`
        : `Remove ${admin.name}?`;
  const action = restoring ? "Restore and send link" : invited ? "Cancel invite" : "Remove";

  return (
    <Dialog
      open={state !== null}
      title={title}
      onClose={onCancel}
      dismissible={!busy}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel} disabled={busy} data-autofocus>
            {invited ? "Keep invite" : "Cancel"}
          </Button>
          <Button onClick={onConfirm} loading={busy}>
            {action}
          </Button>
        </>
      }
    >
      {admin && (
        <div className="flex flex-col gap-4 text-sm text-muted">
          {error && <Alert tone="error">{error}</Alert>}
          <PersonCard admin={admin} />
          <ul className="flex flex-col gap-3">
            {restoring ? (
              <>
                <Consequence icon={Mail}>
                  We&rsquo;ll email {first} a new link to choose a password.
                </Consequence>
                <Consequence icon={KeyRound}>
                  Their old password won&rsquo;t work. Until they choose a new one, they show as{" "}
                  <strong className="font-semibold text-ink">Invite sent</strong>.
                </Consequence>
              </>
            ) : invited ? (
              <>
                <Consequence icon={MailX}>The link in their invite stops working.</Consequence>
                <Consequence icon={RotateCcw}>
                  You can invite them again later, from Removed.
                </Consequence>
              </>
            ) : (
              <>
                <Consequence icon={LogOut}>
                  <strong className="font-semibold text-ink">
                    They&rsquo;re signed out straight away
                  </strong>{" "}
                  and can no longer sign in.
                </Consequence>
                <Consequence icon={BookOpen}>
                  Topics and lessons they worked on stay as they are.
                </Consequence>
                <Consequence icon={Mail}>
                  We&rsquo;ll email {first} to say you removed them.
                </Consequence>
                <Consequence icon={RotateCcw}>You can restore them at any time.</Consequence>
              </>
            )}
          </ul>
        </div>
      )}
    </Dialog>
  );
}
