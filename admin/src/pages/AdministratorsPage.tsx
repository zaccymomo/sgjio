import { Alert, ApiError, Button, ErrorState, Spinner, cn, useAuth } from "@sgjio/ui";
import {
  ChevronDown,
  ChevronLeft,
  Mail,
  MailX,
  RotateCcw,
  Send,
  UserMinus,
  UserPlus,
  X,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { ActivityFeed } from "../components/admins/ActivityFeed";
import {
  AddAdminDialog,
  ConfirmAdminDialog,
  type ConfirmState,
} from "../components/admins/AdminDialogs";
import { Avatar } from "../components/admins/Avatar";
import { RowMenu, type MenuItem } from "../components/RowMenu";
import { adminApi, useAdmins, type Admin } from "../lib/admins";
import type { Notice } from "../lib/content";
import { formatDate, formatDateTime, formatRelative, plural } from "../lib/format";

/** How long a new or restored row stays highlighted. */
const HIGHLIGHT_MS = 2500;

const RELATIVE = new Intl.RelativeTimeFormat("en-SG", { numeric: "auto" });

/** "in 3 days", "in 5 hours", or null once it has passed. */
function timeLeft(iso: string | null, now = Date.now()): string | null {
  if (!iso) return null;
  const hours = (new Date(iso).getTime() - now) / 3_600_000;
  if (hours <= 0) return null;
  // Rounded, so a link sent a moment ago with 72 hours left reads "in 3 days".
  if (hours >= 24) return RELATIVE.format(Math.round(hours / 24), "day");
  return hours >= 1 ? RELATIVE.format(Math.floor(hours), "hour") : "in under an hour";
}

function messageOf(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

/**
 * Administrators (SCRUM-81): everyone who can use the portal, with when they were added
 * and last signed in (AC1); inviting (AC2, AC3), removing (AC4, AC5) and restoring; and the
 * activity log. Reached from the account menu.
 */
export function AdministratorsPage() {
  const { user } = useAuth();
  const { state, reload, retry, recheckSession } = useAdmins();
  const [adding, setAdding] = useState(false);
  const [confirm, setConfirm] = useState<ConfirmState | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [highlight, setHighlight] = useState<string | null>(null);
  const [showRemoved, setShowRemoved] = useState(false);
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    document.title = "Administrators · SGJio admin";
  }, []);

  useEffect(() => {
    if (!highlight) return;
    const timer = window.setTimeout(() => setHighlight(null), HIGHLIGHT_MS);
    return () => window.clearTimeout(timer);
  }, [highlight]);

  /** A change made, then the list and activity loaded again. */
  async function changed(admin: Admin, message: string) {
    setNotice({ tone: "success", message });
    setHighlight(admin.id);
    await reload();
  }

  function sessionEnded(error: unknown): boolean {
    if (error instanceof ApiError && error.status === 401) {
      void recheckSession();
      return true;
    }
    return false;
  }

  /** Throws, so the add dialog can show why; the menu shows it as a message instead. */
  async function resend(id: string) {
    const sent = await adminApi.resendInvite(id);
    setAdding(false);
    await changed(sent, `We've sent ${sent.name} a new invite at ${sent.email}.`);
  }

  async function restore(id: string) {
    const restored = await adminApi.restore(id);
    setAdding(false);
    setShowRemoved(false);
    await changed(
      restored,
      `${restored.name} is back. We've emailed them a link to choose a new password.`,
    );
  }

  async function handleConfirm() {
    if (!confirm) return;
    const { kind, admin } = confirm;
    setBusy(true);
    setConfirmError(null);
    try {
      if (kind === "restore") {
        await restore(admin.id);
      } else {
        const removed = await adminApi.remove(admin.id);
        setShowRemoved(true);
        await changed(
          removed,
          admin.status === "invited"
            ? `${admin.name}'s invite was cancelled. The link no longer works.`
            : `${admin.name} was removed and signed out. We've emailed to let them know.`,
        );
      }
      setConfirm(null);
    } catch (error) {
      if (sessionEnded(error)) return;
      setConfirmError(messageOf(error, "That didn't work. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  function ask(next: ConfirmState) {
    setConfirmError(null);
    setConfirm(next);
  }

  function menuFor(admin: Admin): MenuItem[][] {
    if (admin.status === "invited") {
      return [
        [
          {
            label: "Resend invite",
            icon: Send,
            onSelect: () =>
              void resend(admin.id).catch((error: unknown) => {
                if (sessionEnded(error)) return;
                setNotice({ tone: "error", message: messageOf(error, "We couldn't send it.") });
              }),
          },
        ],
        [
          {
            label: "Cancel invite",
            icon: MailX,
            danger: true,
            onSelect: () => ask({ kind: "remove", admin }),
          },
        ],
      ];
    }
    return [
      [
        {
          label: "Remove",
          icon: UserMinus,
          danger: true,
          onSelect: () => ask({ kind: admin.is_you ? "self" : "remove", admin }),
        },
      ],
    ];
  }

  const data = state.status === "ready" ? state.data : null;
  const active = data?.admins.filter((a) => a.status === "active").length ?? 0;
  const waiting = data?.admins.filter((a) => a.status === "invited").length ?? 0;

  return (
    <div className="flex flex-col gap-5">
      <Link
        to="/"
        className="inline-flex w-fit items-center gap-1 rounded-sm text-sm font-medium text-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
      >
        <ChevronLeft className="size-4" aria-hidden />
        All content
      </Link>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 ref={headingRef} tabIndex={-1} className="text-2xl font-bold text-ink outline-none">
            Administrators
          </h1>
          <p className="mt-1 max-w-xl text-sm text-muted">
            Everyone here has the same access: they can edit topics and lessons, and add or remove
            administrators. Every change is recorded below.
          </p>
        </div>
        <Button className="w-full sm:w-auto" onClick={() => setAdding(true)} disabled={!data}>
          <UserPlus className="size-4" aria-hidden />
          Add administrator
        </Button>
      </div>

      {/* Always present, so messages are announced; takes no space when empty. */}
      <div aria-live="polite" aria-atomic className="empty:-mt-5">
        {notice && (
          <div className="relative">
            <Alert tone={notice.tone} className="pr-10">
              {notice.message}
            </Alert>
            <button
              type="button"
              onClick={() => setNotice(null)}
              aria-label="Dismiss message"
              className="absolute top-1.5 right-1.5 flex size-7 items-center justify-center rounded-sm text-muted hover:bg-black/5 focus-visible:outline-2 focus-visible:outline-brand"
            >
              <X className="size-3.5" aria-hidden />
            </button>
          </div>
        )}
      </div>

      {state.status === "loading" && (
        <div className="flex justify-center py-16 text-brand">
          <Spinner className="size-6" label="Loading administrators" />
        </div>
      )}
      {state.status === "error" && <ErrorState message={state.message} onRetry={retry} />}

      {data && (
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="flex flex-col gap-6">
            <section aria-labelledby="team-heading" className="flex flex-col gap-3">
              <div className="flex items-baseline justify-between gap-3">
                <h2
                  id="team-heading"
                  className="text-caption font-semibold tracking-wide text-muted uppercase"
                >
                  {plural(data.admins.length, "administrator")}
                </h2>
                {waiting > 0 && (
                  <p className="text-xs text-muted">
                    {plural(waiting, "invite")} waiting to be accepted
                  </p>
                )}
              </div>
              <div className="overflow-hidden rounded-lg border border-line bg-white">
                <div
                  aria-hidden
                  className="hidden border-b border-line bg-surface px-4 py-2 text-caption font-semibold tracking-wide text-subtle uppercase sm:grid sm:grid-cols-[minmax(0,1fr)_9.5rem_10.5rem_2.25rem] sm:gap-4"
                >
                  <span>Name</span>
                  <span>Added</span>
                  <span>Last sign-in</span>
                  <span />
                </div>
                <ul className="divide-y divide-line">
                  {data.admins.map((admin) => (
                    <AdminRow
                      key={admin.id}
                      admin={admin}
                      highlighted={highlight === admin.id}
                      action={<RowMenu name={admin.name} groups={menuFor(admin)} />}
                    />
                  ))}
                </ul>
              </div>
            </section>

            {data.removed.length > 0 && (
              <section className="flex flex-col gap-3">
                <button
                  type="button"
                  aria-expanded={showRemoved}
                  aria-controls="removed-list"
                  onClick={() => setShowRemoved(!showRemoved)}
                  className="flex w-fit items-center gap-1.5 rounded-sm text-caption font-semibold tracking-wide text-muted uppercase hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
                >
                  <ChevronDown
                    className={cn("size-4 transition-transform", !showRemoved && "-rotate-90")}
                    aria-hidden
                  />
                  Removed · {data.removed.length}
                </button>
                {showRemoved && (
                  <ul
                    id="removed-list"
                    className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-white"
                  >
                    {data.removed.map((admin) => (
                      <AdminRow
                        key={admin.id}
                        admin={admin}
                        highlighted={highlight === admin.id}
                        action={
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => ask({ kind: "restore", admin })}
                            aria-label={`Restore ${admin.name}`}
                          >
                            <RotateCcw className="size-3.5" aria-hidden />
                            Restore
                          </Button>
                        }
                      />
                    ))}
                  </ul>
                )}
              </section>
            )}
          </div>

          <ActivityFeed activity={data.activity} viewerId={user?.id} />
        </div>
      )}

      {data && (
        <AddAdminDialog
          open={adding}
          domain={data.email_domain}
          inviteHours={data.invite_hours}
          onClose={() => setAdding(false)}
          onInvite={async (name, email, allowOtherDomain) => {
            try {
              const invited = await adminApi.invite(name, email, allowOtherDomain);
              setAdding(false);
              await changed(
                invited,
                `Invite sent to ${invited.email}. Once ${name.split(/\s+/)[0]} chooses a password, they can sign in.`,
              );
            } catch (error) {
              if (!sessionEnded(error)) throw error;
            }
          }}
          onResend={resend}
          onRestore={restore}
        />
      )}
      <ConfirmAdminDialog
        state={confirm}
        onlyAdmin={active <= 1}
        busy={busy}
        error={confirmError}
        onCancel={() => setConfirm(null)}
        onConfirm={() => void handleConfirm()}
      />
    </div>
  );
}

/**
 * One administrator. From 640px up it is a row of columns under the list's headings; on a
 * phone the same facts stack under the name.
 */
function AdminRow({
  admin,
  highlighted,
  action,
}: {
  admin: Admin;
  highlighted: boolean;
  action: ReactNode;
}) {
  const removed = admin.status === "removed";
  const invited = admin.status === "invited";
  const added = (
    <>
      Added {formatDate(admin.added_at)}
      {admin.added_by && <span className="text-subtle"> by {admin.added_by}</span>}
    </>
  );

  return (
    <li
      className={cn(
        "flex items-center gap-3 px-4 py-3.5 transition-colors duration-700",
        "sm:grid sm:gap-4",
        removed
          ? "sm:grid-cols-[minmax(0,1fr)_auto]"
          : "sm:grid-cols-[minmax(0,1fr)_9.5rem_10.5rem_2.25rem]",
        highlighted ? "bg-success-soft" : "bg-white",
      )}
    >
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <Avatar name={admin.name} seed={admin.email} faded={removed} />
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className={cn("font-semibold break-words", removed ? "text-muted" : "text-ink")}>
              {admin.name}
            </span>
            {admin.is_you && (
              <span className="rounded-sm bg-ink px-1.5 py-px text-2xs font-semibold text-white uppercase">
                You
              </span>
            )}
            {invited && <InviteBadge />}
          </p>
          <p className={cn("truncate text-sm", removed ? "text-subtle" : "text-muted")}>
            {admin.email}
          </p>
          {/* On a phone, the columns' facts as lines. */}
          <div className="mt-1 flex flex-col gap-0.5 text-xs text-muted sm:hidden">
            {removed ? (
              <RemovedLine admin={admin} />
            ) : (
              <>
                {invited ? <InviteLine admin={admin} /> : <SignInLine admin={admin} />}
                <span>{added}</span>
              </>
            )}
          </div>
          {removed && (
            <p className="mt-1 hidden text-xs text-muted sm:block">
              <RemovedLine admin={admin} />
            </p>
          )}
        </div>
      </div>

      {!removed && (
        <>
          <p className="hidden text-sm text-muted sm:flex sm:flex-col">
            <span>{formatDate(admin.added_at)}</span>
            {admin.added_by && <span className="text-xs text-subtle">by {admin.added_by}</span>}
          </p>
          <p className="hidden text-sm sm:block">
            {invited ? <InviteLine admin={admin} /> : <SignInLine admin={admin} stacked />}
          </p>
        </>
      )}
      <div className="flex shrink-0 justify-end">{action}</div>
    </li>
  );
}

function InviteBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-px text-caption font-semibold text-amber-800 ring-1 ring-amber-200">
      <Mail className="size-3" aria-hidden />
      Invite sent
    </span>
  );
}

function SignInLine({ admin, stacked = false }: { admin: Admin; stacked?: boolean }) {
  if (!admin.last_sign_in_at) {
    return <span className="text-subtle">{stacked ? "Never" : "Never signed in"}</span>;
  }
  return (
    <time
      dateTime={admin.last_sign_in_at}
      title={formatDateTime(admin.last_sign_in_at)}
      className="text-muted"
    >
      {stacked ? "" : "Last signed in "}
      {formatRelative(admin.last_sign_in_at)}
    </time>
  );
}

/** When the invite went out and how long its link has left, or that it has run out. */
function InviteLine({ admin }: { admin: Admin }) {
  const left = timeLeft(admin.invite_expires_at);
  return (
    <span className="flex flex-col">
      {admin.invited_at && (
        <span className="text-muted">Sent {formatRelative(admin.invited_at)}</span>
      )}
      <span className={cn("text-xs", left ? "text-subtle" : "font-semibold text-amber-700")}>
        {left ? `Link expires ${left}` : "Link expired: resend it"}
      </span>
    </span>
  );
}

function RemovedLine({ admin }: { admin: Admin }) {
  return (
    <span>
      Removed {admin.removed_at ? formatDate(admin.removed_at) : ""}
      {admin.removed_by && <> by {admin.removed_by}</>}
    </span>
  );
}
