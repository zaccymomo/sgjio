import type { ReactNode } from "react";

import { Logo } from "./Logo";

/** The admin portal's frame: a plain top bar, no main-app tabs. */
export function AdminLayout({ actions, children }: { actions?: ReactNode; children: ReactNode }) {
  return (
    <div className="min-h-dvh bg-surface">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4 md:px-6">
          <div className="flex items-center gap-3">
            <Logo />
            <span className="rounded-sm bg-ink px-2 py-0.5 text-2xs font-semibold tracking-wide text-white uppercase">
              Admin
            </span>
          </div>
          {actions && <div className="flex items-center gap-3">{actions}</div>}
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6 md:px-6 md:py-8">{children}</main>
    </div>
  );
}
