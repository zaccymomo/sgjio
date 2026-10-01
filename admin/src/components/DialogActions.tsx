import type { ReactNode } from "react";

/**
 * The button row at the foot of a dialog. Put Cancel first, then the main action: they sit
 * side by side from 640px up, and stack with the main action on top on a phone.
 */
export function DialogActions({ children }: { children: ReactNode }) {
  return (
    <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">{children}</div>
  );
}
