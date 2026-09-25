import { AlertCircle, CheckCircle2, Info } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "../lib/cn";

type Tone = "error" | "info" | "success";

const tones: Record<Tone, { box: string; icon: typeof Info }> = {
  error: { box: "border-danger/30 bg-danger-soft text-danger", icon: AlertCircle },
  info: { box: "border-line bg-surface text-muted", icon: Info },
  success: { box: "border-success/30 bg-success-soft text-success", icon: CheckCircle2 },
};

/** A general message box, e.g. "The email or password is incorrect." */
export function Alert({
  tone = "info",
  children,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}) {
  const { box, icon: Icon } = tones[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn("flex items-start gap-2 rounded-md border px-3 py-2.5 text-sm", box, className)}
    >
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div>{children}</div>
    </div>
  );
}
