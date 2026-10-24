import { cn } from "@sgjio/ui";

import { initials } from "../../lib/admins";

// Soft tints, each with text dark enough to read on it. Written out in full so Tailwind
// finds the class names.
const TINTS = [
  "bg-rose-100 text-rose-700",
  "bg-amber-100 text-amber-800",
  "bg-emerald-100 text-emerald-800",
  "bg-sky-100 text-sky-800",
  "bg-violet-100 text-violet-700",
  "bg-teal-100 text-teal-800",
  "bg-orange-100 text-orange-800",
  "bg-indigo-100 text-indigo-700",
];

/** Always the same tint for the same person, wherever they appear. */
function tintFor(seed: string): string {
  let hash = 0;
  for (const char of seed) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return TINTS[hash % TINTS.length];
}

/**
 * Someone's initials in a circle. `seed` (their email) picks the tint, so a person keeps
 * their colour when their name is edited. Faded for someone removed.
 */
export function Avatar({
  name,
  seed,
  size = "md",
  faded = false,
}: {
  name: string;
  seed: string;
  size?: "sm" | "md";
  faded?: boolean;
}) {
  return (
    <span
      aria-hidden
      className={cn(
        "flex shrink-0 items-center justify-center rounded-full font-semibold tracking-wide select-none",
        size === "sm" ? "size-8 text-xs" : "size-10 text-sm",
        faded ? "bg-surface text-subtle ring-1 ring-line" : tintFor(seed),
      )}
    >
      {initials(name)}
    </span>
  );
}
