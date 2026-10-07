import type { ReactNode } from "react";

import { cn } from "../lib/cn";
import { Logo } from "./Logo";

/**
 * The admin portal's frame: a plain top bar, no main-app tabs. `wide` gives pages that
 * work side by side, such as the lesson editor's three panes, the whole screen.
 */
export function AdminLayout({
  actions,
  wide,
  children,
}: {
  actions?: ReactNode;
  wide?: boolean;
  children: ReactNode;
}) {
  const width = wide ? "max-w-[100rem]" : "max-w-6xl";
  return (
    <div className="min-h-dvh bg-surface">
      <header className="border-b border-line bg-white">
        <div
          className={cn("mx-auto flex h-14 items-center justify-between gap-4 px-4 md:px-6", width)}
        >
          <div className="flex items-center gap-3">
            <Logo />
            <span className="rounded-sm bg-ink px-2 py-0.5 text-2xs font-semibold tracking-wide text-white uppercase">
              Admin
            </span>
          </div>
          {actions && <div className="flex items-center gap-3">{actions}</div>}
        </div>
      </header>
      <main className={cn("mx-auto px-4 py-6 md:px-6 md:py-8", width)}>{children}</main>
    </div>
  );
}
