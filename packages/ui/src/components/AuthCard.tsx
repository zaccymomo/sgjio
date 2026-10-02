import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Logo } from "./Logo";

/** Centred card for sign-in, register and password pages in both apps. */
export function AuthCard({
  title,
  subtitle,
  icon: Icon,
  badge,
  children,
  footer,
}: {
  title: string;
  subtitle?: ReactNode;
  /** Shown in a tinted circle above the title, e.g. a key on "Forgot your password?". */
  icon?: LucideIcon;
  /** Small label next to the logo, e.g. "Admin". */
  badge?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center bg-surface px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-3">
          <Logo size="lg" />
          {badge && (
            <span className="rounded-sm bg-ink px-2 py-0.5 text-2xs font-semibold tracking-wide text-white uppercase">
              {badge}
            </span>
          )}
        </div>
        <div className="rounded-md border border-line bg-white p-6 shadow-sm">
          {Icon && (
            <div className="mb-4 flex size-11 items-center justify-center rounded-full bg-brand-soft text-brand">
              <Icon className="size-5" aria-hidden />
            </div>
          )}
          <h1 className="text-xl font-bold text-ink">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
          <div className="mt-6">{children}</div>
        </div>
        {footer && <div className="mt-4 text-center text-sm text-muted">{footer}</div>}
      </div>
    </div>
  );
}
