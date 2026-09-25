import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

import { cn } from "../lib/cn";
import { Logo } from "./Logo";

export type NavItem = { to: string; label: string; icon: LucideIcon };

/**
 * The main app's frame, from the Figma home screen: a header with the logo and location,
 * and the five-tab navigation.
 *
 * SGJio is a web app and the Figma frames are drawn at phone width, so the layout adapts:
 * - below 768px the tabs sit at the bottom of the screen, as in Figma
 * - from 768px up they move into the header and content is centred with a max width
 */
export function AppShell({
  nav,
  location = "Singapore",
  children,
}: {
  nav: NavItem[];
  location?: string;
  children: ReactNode;
}) {
  return (
    <div className="min-h-dvh bg-white">
      <header className="sticky top-0 z-10 border-b border-line bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-12 max-w-5xl items-center justify-between px-4">
          <NavLink to="/" aria-label="SGJio home">
            <Logo />
          </NavLink>

          <nav aria-label="Main" className="hidden items-center gap-1 md:flex">
            {nav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-2 rounded-sm px-3 py-1.5 text-sm font-medium transition-colors",
                    isActive ? "bg-brand-soft text-brand" : "text-muted hover:text-ink",
                  )
                }
              >
                <item.icon className="size-4" aria-hidden />
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-2 text-caption text-muted md:hidden">
            {location}
            <span className="size-2 rounded-full bg-brand" aria-hidden />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 pt-4 pb-24 md:pt-8 md:pb-12">{children}</main>

      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-10 border-t border-line bg-white pb-[env(safe-area-inset-bottom)] md:hidden"
      >
        <ul className="mx-auto grid max-w-md grid-cols-5">
          {nav.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  cn(
                    "flex flex-col items-center gap-1 py-2.5 text-2xs font-medium",
                    isActive ? "text-brand" : "text-subtle hover:text-muted",
                  )
                }
              >
                <item.icon className="size-5" aria-hidden />
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}
