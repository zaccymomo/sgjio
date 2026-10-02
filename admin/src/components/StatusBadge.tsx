import { cn } from "@sgjio/ui";
import { CircleCheck, EyeOff, PencilLine } from "lucide-react";

import { STATUS_LABELS, type LessonStatus } from "../lib/content";

// Only the icon is tinted. Published is the usual state, so it stays quiet; text stays muted
// so a column of statuses reads as metadata rather than a row of buttons.
const STYLES: Record<LessonStatus, { icon: typeof CircleCheck; iconClass: string }> = {
  draft: { icon: PencilLine, iconClass: "text-subtle" },
  published: { icon: CircleCheck, iconClass: "text-success" },
  withdrawn: { icon: EyeOff, iconClass: "text-subtle" },
};

/** A lesson's status as text and an icon, never colour alone (SCRUM-66 AC1). */
export function StatusBadge({ status }: { status: LessonStatus }) {
  const { icon: Icon, iconClass } = STYLES[status];
  return (
    <span className="inline-flex items-center gap-1.5 text-caption text-muted">
      <Icon className={cn("size-3.5 shrink-0", iconClass)} aria-hidden />
      {STATUS_LABELS[status]}
    </span>
  );
}
