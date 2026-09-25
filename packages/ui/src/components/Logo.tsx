import logoUrl from "../assets/sgjio-logo.png";
import { cn } from "../lib/cn";

/** The SGJio logo lockup from the Figma header: mark plus wordmark. */
export function Logo({ className, size = "md" }: { className?: string; size?: "md" | "lg" }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <img
        src={logoUrl}
        alt=""
        aria-hidden
        className={size === "lg" ? "h-8 w-auto" : "h-[22px] w-auto"}
      />
      <span className={cn("font-bold text-ink", size === "lg" ? "text-2xl" : "text-base")}>
        SGJio
      </span>
    </span>
  );
}
