import { cn } from "@sgjio/ui";
import {
  BadgeCheck,
  History,
  MailX,
  RotateCcw,
  Send,
  Server,
  UserMinus,
  UserPlus,
  type LucideIcon,
} from "lucide-react";
import { useState, type ReactNode } from "react";

import type { Activity, AdminAction } from "../../lib/admins";
import { formatDateTime, formatRelative } from "../../lib/format";

/** How many changes show before "Show more". */
const FIRST = 6;

const STYLES: Record<AdminAction, { icon: LucideIcon; tint: string }> = {
  invited: { icon: UserPlus, tint: "bg-sky-50 text-sky-700" },
  invite_resent: { icon: Send, tint: "bg-sky-50 text-sky-700" },
  joined: { icon: BadgeCheck, tint: "bg-success-soft text-success" },
  invite_cancelled: { icon: MailX, tint: "bg-surface text-muted" },
  removed: { icon: UserMinus, tint: "bg-danger-soft text-danger" },
  restored: { icon: RotateCcw, tint: "bg-success-soft text-success" },
  added: { icon: Server, tint: "bg-surface text-muted" },
};

function Name({ children }: { children: ReactNode }) {
  return <strong className="font-semibold text-ink">{children}</strong>;
}

/** "Yash removed Mei Tan", with "You" for the person reading it. */
function sentence(entry: Activity, viewerId: string | undefined): ReactNode {
  const you = (id: string | null) => id !== null && id === viewerId;
  const actor = you(entry.actor_id) ? "You" : entry.actor_name;
  const target = you(entry.admin_id) ? "you" : entry.admin_name;
  const subject = you(entry.admin_id) ? "You" : entry.admin_name;
  const whose = you(entry.admin_id) ? "your" : `${entry.admin_name}’s`;

  switch (entry.action) {
    case "invited":
      return (
        <>
          <Name>{actor ?? "Someone"}</Name> invited <Name>{target}</Name>
        </>
      );
    case "invite_resent":
      return actor ? (
        <>
          <Name>{actor}</Name> sent <Name>{target}</Name> a new invite
        </>
      ) : (
        <>
          <Name>{subject}</Name> asked for a new invite link
        </>
      );
    case "joined":
      return (
        <>
          <Name>{subject}</Name> joined and chose a password
        </>
      );
    case "invite_cancelled":
      return (
        <>
          <Name>{actor ?? "Someone"}</Name> cancelled <Name>{whose}</Name> invite
        </>
      );
    case "removed":
      return (
        <>
          <Name>{actor ?? "Someone"}</Name> removed <Name>{target}</Name>
        </>
      );
    case "restored":
      return actor ? (
        <>
          <Name>{actor}</Name> restored <Name>{target}</Name>
        </>
      ) : (
        <>
          <Name>{subject}</Name> {subject === "You" ? "were" : "was"} restored on the server
        </>
      );
    case "added":
      return (
        <>
          <Name>{subject}</Name> {subject === "You" ? "were" : "was"} added on the server
        </>
      );
  }
}

/**
 * Who did what to whom, newest first (SCRUM-81). Every administrator has the same access,
 * so this is what keeps changes accountable: nothing happens without showing up here.
 */
export function ActivityFeed({
  activity,
  viewerId,
}: {
  activity: Activity[];
  viewerId: string | undefined;
}) {
  const [showAll, setShowAll] = useState(false);
  const shown = showAll ? activity : activity.slice(0, FIRST);

  return (
    <section
      aria-labelledby="activity-heading"
      className="rounded-lg border border-line bg-white p-4 sm:p-5"
    >
      <div className="flex items-center gap-2">
        <History className="size-4 text-muted" aria-hidden />
        <h2 id="activity-heading" className="text-sm font-semibold text-ink">
          Activity
        </h2>
      </div>
      <p className="mt-0.5 text-xs text-muted">Every change to who has access.</p>

      {activity.length === 0 ? (
        <p className="mt-4 rounded-md bg-surface px-3 py-4 text-center text-sm text-muted">
          Invites, removals and restores will show here.
        </p>
      ) : (
        <ol className="mt-4 flex flex-col">
          {shown.map((entry, index) => {
            const { icon: Icon, tint } = STYLES[entry.action];
            const last = index === shown.length - 1;
            return (
              <li key={entry.id} className="relative flex gap-3 pb-4 last:pb-0">
                {/* The line joining one change to the next. */}
                {!last && (
                  <span
                    className="absolute top-8 bottom-1 left-[0.9375rem] w-px bg-line"
                    aria-hidden
                  />
                )}
                <span
                  className={cn(
                    "relative flex size-8 shrink-0 items-center justify-center rounded-full",
                    tint,
                  )}
                >
                  <Icon className="size-4" aria-hidden />
                </span>
                <div className="min-w-0 pt-1">
                  <p className="text-sm break-words text-muted">{sentence(entry, viewerId)}</p>
                  <time
                    dateTime={entry.at}
                    title={formatDateTime(entry.at)}
                    className="text-caption text-subtle"
                  >
                    {formatRelative(entry.at)}
                  </time>
                </div>
              </li>
            );
          })}
        </ol>
      )}

      {activity.length > FIRST && (
        <button
          type="button"
          onClick={() => setShowAll(!showAll)}
          className="mt-4 w-full rounded-sm py-2 text-xs font-semibold text-muted hover:bg-surface hover:text-ink focus-visible:outline-2 focus-visible:outline-brand"
        >
          {showAll ? "Show less" : `Show ${activity.length - FIRST} more`}
        </button>
      )}
    </section>
  );
}
