import { ApiError, apiFetch, useAuth } from "@sgjio/ui";
import { useCallback, useEffect, useState } from "react";

const ADMINS = "/api/admin/admins";

export type AdminStatus = "active" | "invited" | "removed";

/** An administrator as /api/admin/admins returns it (SCRUM-81). */
export type Admin = {
  id: string;
  name: string;
  email: string;
  status: AdminStatus;
  added_at: string;
  /** Who invited them. Empty for accounts that were seeded or made on the server. */
  added_by: string | null;
  /** The last successful sign-in to the portal. */
  last_sign_in_at: string | null;
  /** When the latest invite was sent, while they have not chosen a password. */
  invited_at: string | null;
  invite_expires_at: string | null;
  removed_at: string | null;
  removed_by: string | null;
  is_you: boolean;
};

export type AdminAction =
  "invited" | "invite_resent" | "joined" | "invite_cancelled" | "removed" | "restored" | "added";

/** One change to an administrator account. No actor: the person themselves, or the server. */
export type Activity = {
  id: string;
  action: AdminAction;
  at: string;
  admin_id: string;
  admin_name: string;
  actor_id: string | null;
  actor_name: string | null;
};

export type AdminsData = {
  /** Active and invited, by name. */
  admins: Admin[];
  /** Most recently removed first. */
  removed: Admin[];
  /** Latest first. */
  activity: Activity[];
  /** Emails outside it ask for confirmation. Null: no check. */
  email_domain: string | null;
  /** How long an invite link lasts. */
  invite_hours: number;
};

export const adminApi = {
  invite: (name: string, email: string, allowOtherDomain: boolean) =>
    apiFetch<Admin>(ADMINS, {
      method: "POST",
      body: { name, email, allow_other_domain: allowOtherDomain },
    }),
  resendInvite: (id: string) =>
    apiFetch<Admin>(`${ADMINS}/${id}/resend-invite`, { method: "POST" }),
  remove: (id: string) => apiFetch<Admin>(`${ADMINS}/${id}/remove`, { method: "POST" }),
  restore: (id: string) => apiFetch<Admin>(`${ADMINS}/${id}/restore`, { method: "POST" }),
};

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: AdminsData };

/**
 * Loads the Administrators page. `reload` fetches again quietly, keeping the list on screen,
 * and so does the tab regaining focus, so a change made in another browser shows up. A 401
 * re-checks the session, so a removed administrator is sent to sign in.
 */
export function useAdmins() {
  const { refresh: recheckSession } = useAuth();
  const [state, setState] = useState<State>({ status: "loading" });

  // Returns what to show rather than setting it, so the effect below sets state only in
  // a callback. `null`: nothing to show, as the request was cancelled or the session ended.
  const fetchData = useCallback(
    async (signal?: AbortSignal): Promise<AdminsData | Error | null> => {
      try {
        return await apiFetch<AdminsData>(ADMINS, { signal });
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return null;
        if (error instanceof ApiError && error.status === 401) {
          void recheckSession();
          return null;
        }
        return new Error("We couldn't load the administrators. Please try again.");
      }
    },
    [recheckSession],
  );

  const apply = useCallback((result: AdminsData | Error | null) => {
    if (result === null) return;
    if (result instanceof Error) {
      // Keep a list already on screen; a failed quiet refresh changes nothing.
      setState((current) =>
        current.status === "ready" ? current : { status: "error", message: result.message },
      );
    } else {
      setState({ status: "ready", data: result });
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void fetchData(controller.signal).then(apply);
    const onFocus = () => void fetchData().then(apply);
    window.addEventListener("focus", onFocus);
    return () => {
      controller.abort();
      window.removeEventListener("focus", onFocus);
    };
  }, [fetchData, apply]);

  const reload = useCallback(async () => apply(await fetchData()), [fetchData, apply]);

  const retry = useCallback(() => {
    setState({ status: "loading" });
    void reload();
  }, [reload]);

  return { state, reload, retry, recheckSession };
}

/** "Mei Ling Tan" -> "MT", "arjun" -> "A". */
export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  const first = words[0][0];
  const last = words.length > 1 ? words[words.length - 1][0] : "";
  return (first + last).toUpperCase();
}

/** The part of an email after the @, lower-case. */
export function emailDomain(email: string): string {
  return email.trim().toLowerCase().split("@").pop() ?? "";
}

/** "3 days", "12 hours", as the invite email says it. */
export function inviteLifetime(hours: number): string {
  if (hours % 24 === 0) {
    const days = hours / 24;
    return `${days} day${days === 1 ? "" : "s"}`;
  }
  return `${hours} hour${hours === 1 ? "" : "s"}`;
}
